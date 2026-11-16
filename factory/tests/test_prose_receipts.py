"""Prose warnings ride on delivery receipts without changing their verdict."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from dotfactory import delivery
import test_verified_delivery as delivery_fixture
from test_verified_delivery import ApprovedRuntime, EditingRunner

SLOP = "\n\nThis change serves as a pivotal step. I hope this helps.\n"


class ProseReceiptTests(unittest.TestCase):
    setUp = delivery_fixture.VerifiedDeliveryTests.setUp
    tearDown = delivery_fixture.VerifiedDeliveryTests.tearDown

    def receipts(self, runner, until="Review"):
        with ApprovedRuntime(self.config, runner=runner) as runtime:
            execution = runtime.start_issue("demo", "DEMO-1", description="Return こんにちは")
            runtime.run([execution], until_state=until, max_ticks=20)
            rows = runtime.ledger.connection.execute(
                "SELECT payload_json FROM events WHERE event_type='delivery_checked' ORDER BY seq").fetchall()
            return [json.loads(row[0]) for row in rows], runtime.ledger.current(execution)["current_state_id"]

    def test_warnings_are_recorded_and_verdicts_match_a_clean_run(self):
        clean, clean_state = self.receipts(EditingRunner())
        self.tearDown()
        self.setUp()
        sloppy, sloppy_state = self.receipts(EditingRunner(slop=SLOP))
        self.assertEqual("Review", sloppy_state)
        self.assertEqual(clean_state, sloppy_state)
        self.assertEqual([(r["contract"], r["passed"]) for r in clean],
                         [(r["contract"], r["passed"]) for r in sloppy])
        self.assertFalse(any("prose_warnings" in r for r in clean))
        by_contract = {r["contract"]: r for r in sloppy}
        plan = by_contract["plan-result-v2"]["prose_warnings"]
        self.assertEqual({".factory/plan.md"}, {item["source"] for item in plan})
        self.assertEqual(["copula-avoidance", "ai-vocabulary", "chatbot-frame"], [item["pattern"] for item in plan])
        for contract in ("implementation-result-v2", "python-verification-v2"):
            self.assertEqual({"delivery.json summary"},
                             {item["source"] for item in by_contract[contract]["prose_warnings"]})

    def test_warnings_never_rescue_or_fail_a_receipt(self):
        clean, _ = self.receipts(EditingRunner(missing=True), until="PlanReview")
        self.tearDown()
        self.setUp()
        sloppy, _ = self.receipts(EditingRunner(missing=True, slop=SLOP), until="PlanReview")
        self.assertEqual([(r["contract"], r["passed"], r.get("error")) for r in clean],
                         [(r["contract"], r["passed"], r.get("error")) for r in sloppy])
        self.assertFalse(sloppy[0]["passed"])
        self.assertTrue(sloppy[0]["prose_warnings"])

    def test_unreadable_or_absent_files_are_skipped(self):
        root = self.root / "repository"
        self.assertEqual([], delivery.prose_warnings(root, "implementation-result-v2", {}))
        with patch("dotfactory.delivery.local_file", side_effect=OSError("denied")):
            found = delivery.prose_warnings(root, "python-verification-v2",
                                            {"delivery": {"summary": "We delve."}})
        self.assertEqual([{"pattern": "ai-vocabulary", "source": "delivery.json summary", "line": 1,
                           "text": "delve"}], found)


if __name__ == "__main__":
    unittest.main()
