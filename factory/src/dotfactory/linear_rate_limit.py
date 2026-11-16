"""Coordinate Linear API cooldowns and retain only rate-limit metadata."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

RATE_LIMIT_CODES = frozenset({"HTTP_429", "RATELIMITED", "RATE_LIMITED"})
HEADER_GROUPS = {
    "requests": "Requests",
    "operation": "Endpoint-Requests",
    "complexity": "Complexity",
}
MAX_OBSERVATIONS = 100
DEFAULT_BACKOFF = 30
COOLDOWN_CODE = "linear_rate_limit_cooldown"


def number(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,14}", value.strip()):
        return int(value)


def label(value):
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,95}", value):
        return value


def retry_after(value, now):
    seconds = number(value)
    if seconds is not None:
        return seconds
    if value:
        try:
            date = parsedate_to_datetime(value)
            return max(0, date.replace(tzinfo=date.tzinfo or timezone.utc).timestamp() - now)
        except (ValueError, TypeError, OverflowError, OSError):
            return None
    return None


def provider_observation(operation, headers, now):
    headers = {name.lower(): value for name, value in (headers or {}).items()}
    complexity = number(headers.get("x-complexity"))
    budgets = {}
    exhausted = []
    for quota, header in HEADER_GROUPS.items():
        prefix = "x-ratelimit-" + header.lower() + "-"
        budget = {field: amount for field in ("limit", "remaining", "reset")
                  if (amount := number(headers.get(prefix + field))) is not None}
        if budget:
            budgets[quota] = budget
        remaining = budget.get("remaining")
        if remaining is not None and remaining < ((complexity or 1) if quota == "complexity" else 1):
            exhausted.append(quota)
    endpoint_operation = label(headers.get("x-ratelimit-endpoint-name"))
    if endpoint_operation and "remaining" not in budgets.get("operation", {}):
        exhausted.append("operation")
    delay = retry_after(headers.get("retry-after"), now)
    resets = [budgets[quota]["reset"] / 1000 for quota in exhausted if "reset" in budgets.get(quota, {})]
    until = now + delay if delay is not None else max([now + DEFAULT_BACKOFF, *resets])
    return {
        "operation": label(operation),
        "endpoint_operation": endpoint_operation,
        "exhausted": exhausted,
        "budgets": budgets,
        "complexity": complexity,
        "retry_at": until,
        "retry_after": delay,
        "observed_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
    }


def _write_state(path, state):
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".linear-")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class LinearCooldown:
    def __init__(self, directory: Path, endpoint: str, authorization: str, *,
                 actor: tuple[str, str] | None = None, project: str | None = None,
                 clock=time.time):
        # Actor-scoped store survives token rotation. Unbound credentials share only
        # when they are identical. The local key is never included in a receipt.
        identity = ["actor", *actor] if actor else ["credential", authorization.strip().removeprefix("Bearer ")]
        self.key = hashlib.sha256(json.dumps([endpoint, *identity]).encode()).hexdigest()
        self.path = directory / "activity.json"
        self.project = label(project)
        self.clock = clock

    def _state(self):
        try:
            with self.path.open() as handle:
                return json.load(handle)
        except FileNotFoundError:
            return {"version": 1, "cooldowns": {}, "observations": []}

    def pending(self):
        record = self._state()["cooldowns"].get(self.key)
        return record if record and record["retry_at"] > self.clock() else None

    def observe(self, operation, code, headers):
        now = self.clock()
        result = provider_observation(operation, headers, now)
        result.update(id=uuid.uuid4().hex, project=self.project, code=code)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock = os.open(self.path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(lock, "rb") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            state = self._state()
            active = {key: value for key, value in state["cooldowns"].items() if value["retry_at"] > now}
            prior = active.get(self.key)
            if not prior or result["retry_at"] >= prior["retry_at"]:
                active[self.key] = result
            history = (state["observations"] + [result])[-MAX_OBSERVATIONS:]
            _write_state(self.path, {"version": 1, "cooldowns": active, "observations": history})
        return result
