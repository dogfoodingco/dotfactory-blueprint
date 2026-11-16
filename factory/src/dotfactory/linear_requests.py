"""Host-local request counts, with one aggregate per operation and UTC minute."""
from __future__ import annotations

import os
import sqlite3
import sys
import time

from .linear_rate_limit import label

RETENTION_MINUTES = 24 * 60


class LinearRequestCounts:
    def __init__(self, directory, project, *, clock=time.time):
        self.directory = directory
        self.path = directory / "linear-requests.sqlite3"
        self.project = project
        self.clock = clock
        self._last_warning = float("-inf")

    def _connect(self):
        if not self.path.exists():
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.close(os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600))
        return sqlite3.connect(self.path, timeout=0.25)

    def record(self, operation, outcome):
        operation = label(operation)
        if not operation:
            return
        minute = int(self.clock()) // 60
        db = None
        try:
            db = self._connect()
            with db:
                db.execute("""CREATE TABLE IF NOT EXISTS request_minutes (
                    minute INTEGER NOT NULL, project TEXT NOT NULL, operation TEXT NOT NULL,
                    outcome TEXT NOT NULL, count INTEGER NOT NULL,
                    PRIMARY KEY(minute, project, operation, outcome)) WITHOUT ROWID""")
                db.execute("""INSERT INTO request_minutes VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(minute, project, operation, outcome)
                    DO UPDATE SET count=count+1""", (minute, self.project, operation, outcome))
                db.execute("DELETE FROM request_minutes WHERE minute < ?", (minute - RETENTION_MINUTES + 1,))
        except (OSError, sqlite3.Error) as error:
            now = time.monotonic()
            if now - self._last_warning >= 60:
                self._last_warning = now
                print(f"Linear request counts unavailable for {self.project}: {type(error).__name__}",
                      file=sys.stderr, flush=True)
        finally:
            if db is not None:
                db.close()
