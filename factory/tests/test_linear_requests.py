import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from dotfactory.linear_api import LinearAPIError, LinearGraphQLClient
from dotfactory.linear_rate_limit import LinearCooldown
from dotfactory.linear_requests import LinearRequestCounts


class LinearRequestCountsTests(unittest.TestCase):
    def test_host_aggregation_counts_transport_calls_and_excludes_cooldown(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            counts = LinearRequestCounts(root, "example-b", clock=lambda: 600)
            client = LinearGraphQLClient("fixture", request_counts=counts, transport=lambda *_: {"data": {"viewer": {"id": "actor"}}})
            self.assertEqual("actor", client.viewer_id())
            script = """
from pathlib import Path
import sys
from dotfactory.linear_api import LinearAPIError, LinearGraphQLClient
from dotfactory.linear_rate_limit import LinearCooldown
from dotfactory.linear_requests import LinearRequestCounts

def limit(*_):
    raise LinearAPIError("http_429", "limited", retryable=True, headers={"Retry-After": "30"})

root = Path(sys.argv[1])
limiter = LinearCooldown(root, "https://api.linear.app/graphql", "fixture", clock=lambda: 600)
meter = LinearRequestCounts(root, "example-a", clock=lambda: 600)
client = LinearGraphQLClient("fixture", cooldown=limiter, request_counts=meter, transport=limit)
for _ in range(2):
    try:
        client.viewer_id()
    except LinearAPIError:
        continue
    raise AssertionError("expected rate limit")
"""
            subprocess.run([sys.executable, "-c", script, str(root)], check=True)
            with sqlite3.connect(counts.path) as db:
                seen = db.execute("SELECT minute,project,operation,outcome,count FROM request_minutes ORDER BY project").fetchall()
            self.assertEqual([(10, "example-a", "FactoryViewer", "rate_limited", 1),
                              (10, "example-b", "FactoryViewer", "success", 1)], seen)
            self.assertNotIn("fixture", json.dumps(seen))

    def test_old_minutes_are_pruned(self):
        with TemporaryDirectory() as tmp:
            minute = 10
            counts = LinearRequestCounts(Path(tmp), "example-b", clock=lambda: minute * 60)
            counts.record("FactoryViewer", "success")
            minute += 1440
            counts.record("FactoryViewer", "success")
            with sqlite3.connect(counts.path) as db:
                self.assertEqual([(1450, 1)], db.execute("SELECT minute,count FROM request_minutes").fetchall())
