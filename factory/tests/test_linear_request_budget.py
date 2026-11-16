import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from dotfactory.linear_api import LinearAPIError, LinearGraphQLClient
from dotfactory.linear_rate_limit import COOLDOWN_CODE, LinearCooldown
from dotfactory.linear_planning import read_control_session
from dotfactory.linear_request_budget import RESERVE_CODE, LinearRequestBudget, request_priority
from dotfactory.linear_transport import GraphQLResponse


def request_headers(remaining):
    return {"x-ratelimit-requests-limit": "100", "x-ratelimit-requests-remaining": str(remaining)}


class RequestBudgetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.now = 1000
        self.remaining = 21
        self.operations = []

    def client(self, project, actor="app"):
        store = LinearCooldown(self.root, "fixture", project, actor=("organization", actor),
                               project=project, clock=lambda: self.now)

        def transport(_endpoint, _headers, body, _timeout):
            self.operations.append(json.loads(body)["operationName"])
            session = {"id": "session", "appUser": {"id": "agent"}, "issue": {"id": "issue"},
                       "activities": {"nodes": [], "pageInfo": {"hasNextPage": False}}}
            return GraphQLResponse({"data": {"agentSession": session, "organization": {"id": "organization"}}},
                                   request_headers(self.remaining))

        return LinearGraphQLClient(project, transport=transport, cooldown=store,
                                   request_budget=LinearRequestBudget(self.root, store.key, clock=lambda: self.now))

    def test_shared_reserve_preserves_control_capacity_and_honors_retry_after(self):
        alpha, beta = self.client("alpha"), self.client("beta")
        alpha.execute("LearnBudget", "", {})
        self.remaining = 20
        beta.execute("LastBackground", "", {})
        with self.assertRaises(LinearAPIError) as deferred:
            alpha.execute("Background", "", {})
        self.assertEqual(RESERVE_CODE, deferred.exception.code)
        other = self.client("isolated", actor="other")
        other.execute("OtherActor", "", {})
        self.remaining = 2
        self.assertEqual("session", read_control_session(alpha, "session")["id"])
        with self.assertRaises(LinearAPIError) as deferred:
            read_control_session(beta, "session")
        self.assertEqual(RESERVE_CODE, deferred.exception.code)
        self.remaining = 1
        with request_priority("command"):
            beta.execute("Reply", "", {})
            alpha.cooldown.observe("OtherConsumer", "http_429", {"Retry-After": "60"})
            with self.assertRaises(LinearAPIError) as cooldown:
                alpha.execute("AnotherReply", "", {})
        self.assertEqual(COOLDOWN_CODE, cooldown.exception.code)
        self.assertEqual(["LearnBudget", "LastBackground", "OtherActor", "FactoryPlanningSession", "Reply"], self.operations)

    def test_parallel_processes_cannot_both_spend_last_background_slot(self):
        client = self.client("alpha")
        client.execute("LearnBudget", "", {})
        child = """
import sys
from pathlib import Path
from dotfactory.linear_request_budget import LinearRequestBudget
from dotfactory.linear_transport import LinearAPIError
budget = LinearRequestBudget(Path(sys.argv[1]), sys.argv[2], clock=lambda: 1000)
try:
    budget.admit()
except LinearAPIError as error:
    print(error.code)
else:
    print('admitted')
"""
        args = [sys.executable, "-c", child, str(self.root), client.cooldown.key]
        with subprocess.Popen(args, stdout=subprocess.PIPE, text=True) as first, \
                subprocess.Popen(args, stdout=subprocess.PIPE, text=True) as second:
            answers = [first.communicate(timeout=5)[0].strip(), second.communicate(timeout=5)[0].strip()]
        self.assertCountEqual(["admitted", RESERVE_CODE], answers)

    def test_old_response_cannot_refill_shared_quota_and_capacity_recovers_with_time(self):
        client = self.client("alpha")
        budget = client.request_budget
        older, newer = budget.admit(), budget.admit()
        budget.observe(newer, request_headers(20))
        budget.observe(older, request_headers(95))
        with self.assertRaises(LinearAPIError) as error:
            budget.admit()
        self.assertEqual(1036, error.exception.rate_limit["retry_at"])
        self.now += 36
        self.assertEqual(3, budget.admit())
