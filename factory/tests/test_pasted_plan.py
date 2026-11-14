"""Pasted-plan check: fixture handoffs that paste or point at the frozen plan."""
import contextlib
import io
import json
import unittest
from pathlib import Path

from dotfactory import pasted_plan

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pasted_plan"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def handoff(name):
    return pasted_plan.handoff_prose(json.loads(fixture(name)))


class PastedPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = fixture("plan.md")

    def test_handoff_that_pastes_the_behavior_section_fails(self):
        result = pasted_plan.report(handoff("handoff-pasted.json"), self.plan)
        self.assertTrue(result["pasted"])
        self.assertEqual(2, len(result["runs"]))
        self.assertGreaterEqual(result["longest_run"], 25)
        self.assertIn("recomputes the total within one second", result["runs"][0]["excerpt"])

    def test_handoff_that_points_at_the_plan_passes(self):
        result = pasted_plan.report(handoff("handoff-pointer.json"), self.plan)
        self.assertTrue(result["measurable"])
        self.assertFalse(result["pasted"], result["runs"])
        self.assertEqual(0, result["copied_words"])

    def test_paste_with_changed_capitalization_still_counts(self):
        sentence = self.plan.split("After: ", 1)[1].split("\n", 1)[0]
        self.assertTrue(pasted_plan.report(f"Done. {sentence.upper()}", self.plan)["pasted"])

    def test_paste_inside_a_code_fence_still_counts(self):
        sentence = self.plan.split("After: ", 1)[1].split("\n", 1)[0]
        result = pasted_plan.report(f"Done.\n\n```\n{sentence}\n```\n", self.plan)
        self.assertTrue(result["pasted"])

    def test_threshold_boundary(self):
        plan = "one two three four five six seven eight nine ten eleven twelve thirteen"
        eleven = "x " + " ".join(plan.split()[:11]) + " y"
        twelve = "x " + " ".join(plan.split()[:12]) + " y"
        self.assertEqual([], pasted_plan.scan(eleven, plan))
        self.assertEqual([12], [run.words for run in pasted_plan.scan(twelve, plan)])

    def test_pointers_and_headings_are_not_words(self):
        text = ("## Behavior\n## Out of scope\n## Risks\n"
                "`.factory/plan.md` git:abc123?path=.factory/plan.md factory/tests/test_refunds.py "
                "https://issues.example.com/EX-12")
        self.assertEqual([], pasted_plan.words(text))

    def test_empty_and_short_plans_are_unmeasurable_not_clean(self):
        text = handoff("handoff-pasted.json")
        for plan in ("", "## Purpose\nShort plan.\n"):
            result = pasted_plan.report(text, plan)
            self.assertFalse(result["measurable"])
            self.assertFalse(result["pasted"])
        self.assertEqual([], pasted_plan.scan("", self.plan))
        self.assertEqual(0, pasted_plan.report("", self.plan)["text_words"])

    def test_deterministic_and_offsets_index_the_original(self):
        text = handoff("handoff-pasted.json")
        self.assertEqual(pasted_plan.report(text, self.plan), pasted_plan.report(text, self.plan))
        for run in pasted_plan.scan(text, self.plan):
            self.assertEqual(run.text, text[run.start:run.end])

    def test_handoff_prose_skips_ids_and_uris(self):
        text = handoff("handoff-pointer.json")
        self.assertNotIn("01a1f000", text)
        self.assertIn("The badge is missing", text)

    def test_cli_exit_codes(self):
        plan = str(FIXTURES / "plan.md")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(1, pasted_plan.main([plan, str(FIXTURES / "handoff-pasted.json")]))
            self.assertEqual(0, pasted_plan.main([plan, str(FIXTURES / "handoff-pointer.json")]))
        self.assertTrue(json.loads(out.getvalue().splitlines()[0])["pasted"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, pasted_plan.main([plan]))


if __name__ == "__main__":
    unittest.main()
