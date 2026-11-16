"""Share provider request headroom between coordinators using the same Linear actor."""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from contextvars import ContextVar

from .linear_rate_limit import number
from .linear_transport import LinearAPIError

RESERVE_CODE = "linear_request_reserve"
_PRIORITY = ContextVar("linear_request_priority", default="background")


@contextmanager
def request_priority(priority):
    token = _PRIORITY.set(priority)
    try:
        yield
    finally:
        _PRIORITY.reset(token)


class LinearRequestBudget:
    def __init__(self, directory, scope, *, clock=time.time):
        self.directory = directory
        self.path = directory / "requests.sqlite3"
        self.scope = scope
        self.clock = clock
        self._last_warning = float("-inf")

    def _connect(self):
        if not self.path.exists():
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.close(os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600))
        return sqlite3.connect(self.path, timeout=0.25)

    @contextmanager
    def _state(self):
        with closing(self._connect()) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS request_budget (
                scope TEXT PRIMARY KEY, issued INTEGER NOT NULL, capacity INTEGER,
                available REAL, updated_at REAL NOT NULL, sampled_at REAL,
                reported_remaining INTEGER
            ) WITHOUT ROWID""")
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO request_budget VALUES (?,0,NULL,NULL,0,NULL,NULL)", (self.scope,))
            yield db, db.execute(
                """SELECT issued,capacity,available,updated_at
                FROM request_budget WHERE scope=?""", (self.scope,)
            ).fetchone()

    @staticmethod
    def _available(capacity, available, updated, now):
        return min(capacity, available + max(0, now - updated) * capacity / 3600)

    def admit(self):
        """Deduct in-flight requests under a shared lock before releasing it for HTTP."""
        try:
            with self._state() as (db, state):
                issued, capacity, available, updated = state
                now = max(updated, self.clock())
                if capacity is not None:
                    available = self._available(capacity, available, updated, now)
                    floor = {"background": capacity // 5, "probe": capacity // 50, "command": 0}[_PRIORITY.get()]
                    if available < floor + 1:
                        error = LinearAPIError(RESERVE_CODE, "Linear request quota reserved for commands", retryable=True)
                        error.rate_limit = {"retry_at": now + (floor + 1 - available) * 3600 / capacity}
                        raise error
                    available -= 1
                db.execute("UPDATE request_budget SET issued=?,available=?,updated_at=? WHERE scope=?",
                           (issued + 1, available, now, self.scope))
                return issued + 1
        except (OSError, sqlite3.Error) as error:
            failure = LinearAPIError("linear_request_budget_unavailable", "Linear request budget unavailable", retryable=True)
            failure.rate_limit = {"retry_at": self.clock() + 5}
            raise failure from error

    def observe(self, ticket, headers):
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        limit = number(headers.get("x-ratelimit-requests-limit"))
        remaining = number(headers.get("x-ratelimit-requests-remaining"))
        if not limit or remaining is None or remaining > limit:
            return
        try:
            with self._state() as (db, state):
                issued, capacity, available, updated = state
                now = max(updated, self.clock())
                # Parallel responses can arrive out of order. Account for requests
                # admitted after this one and never refill from a higher response.
                estimate = max(0, remaining - (issued - ticket))
                if capacity is not None:
                    estimate = min(estimate, self._available(capacity, available, updated, now))
                db.execute("""UPDATE request_budget SET capacity=?,available=?,updated_at=?,sampled_at=?,
                    reported_remaining=? WHERE scope=?""", (limit, estimate, now, now, remaining, self.scope))
        except (OSError, sqlite3.Error) as error:
            # The request already happened. A diagnostic write cannot make it safe to repeat.
            now = time.monotonic()
            if now - self._last_warning >= 60:
                self._last_warning = now
                print(f"Linear request budget observation unavailable: {type(error).__name__}",
                      file=sys.stderr, flush=True)
