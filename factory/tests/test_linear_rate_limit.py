import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from dotfactory.linear_api import LinearAPIError, LinearGraphQLClient
from dotfactory.linear_rate_limit import COOLDOWN_CODE, LinearCooldown, provider_observation
from dotfactory.linear_transport import GraphQLResponse


ENDPOINT = "https://example.invalid/graphql"
ACTOR = ("workspace-fixture", "actor-fixture")


class LinearRateLimitTests(unittest.TestCase):
    def test_http_429_honors_retry_after_across_processes_and_preserves_only_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LinearCooldown(Path(tmp), ENDPOINT, "test-credential", actor=ACTOR, project="project-one", clock=lambda: 1000)
            client = LinearGraphQLClient("test-credential", endpoint=ENDPOINT, cooldown=store)
            headers = {
                "Retry-After": "65",
                "X-RateLimit-Endpoint-Requests-Remaining": "0",
                "X-RateLimit-Endpoint-Name": "comments",
                "X-RateLimit-Requests-Remaining": "40",
                "Set-Cookie": "private-fixture",
            }
            failure = HTTPError(ENDPOINT, 429, "Throttled", headers, None)
            with patch("urllib.request.urlopen", side_effect=failure):
                with self.assertRaises(LinearAPIError) as found:
                    client.execute("FactoryPlanningSession", "", {"secret": "private-fixture"})
            row = found.exception.rate_limit
            self.assertEqual(["operation"], row["exhausted"])
            self.assertEqual("comments", row["endpoint_operation"])
            self.assertEqual(1065, row["retry_at"])
            self.assertNotIn("private-fixture", store.path.read_text())
            self.assertNotIn("test-credential", store.path.read_text())

            script = """
import sys
from pathlib import Path
from dotfactory.linear_api import LinearAPIError, LinearGraphQLClient
from dotfactory.linear_rate_limit import LinearCooldown
def send(*args):
    print("sent")
    return {"data": {}}
store = LinearCooldown(Path(sys.argv[1]), sys.argv[2], "another-token", actor=(sys.argv[3], sys.argv[4]),
                       project="project-two", clock=lambda: int(sys.argv[5]))
client = LinearGraphQLClient("another-token", endpoint=sys.argv[2], transport=send, cooldown=store)
try:
    client.execute("FactoryPlanningSession", "", {})
except LinearAPIError as error:
    print(error.code, error.rate_limit["operation"])
"""
            def check(actor, now):
                return subprocess.check_output([sys.executable, "-c", script, tmp, ENDPOINT, *actor, str(now)], text=True).strip()
            self.assertEqual(f"{COOLDOWN_CODE} FactoryPlanningSession", check(ACTOR, 1064))
            self.assertEqual("sent", check(ACTOR, 1065))
            self.assertEqual("sent", check(("workspace-fixture", "other-actor"), 1001))
            self.assertEqual(1, len(json.loads(store.path.read_text())["observations"]))

    def test_graphql_rate_limit_reports_complexity_and_keeps_longest_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LinearCooldown(Path(tmp), ENDPOINT, "key", clock=lambda: 1000)
            equivalent = LinearCooldown(Path(tmp), ENDPOINT, "Bearer key", clock=lambda: 1010)
            response = GraphQLResponse({"errors": [{"extensions": {"code": "RATELIMITED"}}]}, {
                "Retry-After": "120", "X-Complexity": "50", "X-RateLimit-Complexity-Remaining": "49",
                "X-RateLimit-Requests-Remaining": "10",
            })
            client = LinearGraphQLClient("key", transport=lambda *_: response, cooldown=store)
            with self.assertRaises(LinearAPIError) as found:
                client.execute("FactoryPlanningSession", "", {})
            self.assertEqual(["complexity"], found.exception.rate_limit["exhausted"])
            self.assertEqual(1120, equivalent.pending()["retry_at"])

            # An earlier in-flight request can finish after another process published its cooldown.
            equivalent.observe("FactoryIssue", "http_429", {"Retry-After": "5"})
            self.assertEqual(1120, equivalent.pending()["retry_at"])
            self.assertEqual("FactoryPlanningSession", equivalent.pending()["operation"])
            self.assertEqual(2, len(json.loads(store.path.read_text())["observations"]))

            with self.assertRaises(LinearAPIError) as deferred:
                client.create_agent_activity(session_id="session", activity_id="activity", content={})
            self.assertEqual(COOLDOWN_CODE, deferred.exception.code)
            self.assertFalse(deferred.exception.ambiguous)

    def test_parse_known_quotas_and_fallback_when_provider_omits_retry_after(self):
        explicit = provider_observation("FactoryIssue", {
            "Retry-After": "Thu, 01 Jan 1970 00:18:20 GMT",
            "X-RateLimit-Requests-Remaining": "0",
            "X-RateLimit-Requests-Reset": "1200000",
        }, 1000)
        self.assertEqual(1100, explicit["retry_at"])
        self.assertEqual(["requests"], explicit["exhausted"])
        fallback = provider_observation("FactoryIssue", {
            "Retry-After": "malformed", "X-RateLimit-Requests-Remaining": "0",
            "X-RateLimit-Requests-Reset": "1200000",
        }, 1000)
        self.assertEqual(1200, fallback["retry_at"])
        self.assertIsNone(fallback["retry_after"])
        endpoint_only = provider_observation("FactoryIssue", {"X-RateLimit-Endpoint-Name": "issue"}, 1000)
        self.assertEqual(["operation"], endpoint_only["exhausted"])
        missing = provider_observation("FactoryIssue", {}, 1000)
        self.assertEqual([], missing["exhausted"])
        self.assertEqual(1030, missing["retry_at"])

    def test_supervised_startup_keeps_operator_access_during_initial_cooldown(self):
        from dotfactory.cli import _demo_config
        from dotfactory.instance import FactoryConfig
        from dotfactory.lifecycle import FactoryRuntime, fixture_runner
        from dotfactory.work_queue import WorkQueue
        from dotfactory.work_queue import WorkQueue

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        config = FactoryConfig.load(_demo_config(root))
        values = json.loads(config.path.read_text())
        values["work_queue"] = {"enabled": True, "admission_label": "test-ready"}
        values["projections"]["linear"]["enabled"] = True
        values["work_queue"] = {"enabled": True, "admission_label": "ready-for-factory"}
        values["projects"]["demo"]["tracker"]["team_id"] = "test-team"
        config.path.write_text(json.dumps(values))
        config = FactoryConfig.load(config.path)
        env = {"DOTFACTORY_HOME": str(root), "LINEAR_API_KEY": "test-credential"}
        path = root / "linear-rate-limit"
        store = LinearCooldown(path, "https://api.linear.app/graphql", "test-credential")
        store.observe("FactoryLinearPreflight", "http_429", {"Retry-After": "180"})

        with patch("urllib.request.urlopen") as send:
            with FactoryRuntime(config, runner=fixture_runner(), environment=env,
                                defer_linear_preflight=True) as runtime:
                queue = WorkQueue(runtime)
                queue = WorkQueue(runtime)
                runtime.enable_operator()
                self.assertIsNotNone(runtime.operator_server)
                self.assertFalse(runtime.linear_workers)
                result = queue.step()
                self.assertEqual("tracker_unavailable", result["status"])
                send.assert_not_called()
