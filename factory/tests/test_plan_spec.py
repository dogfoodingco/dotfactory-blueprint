"""ADR-0112 contract: plan sections (D1), model criteria (F3), spec findings (D3)."""
import json
import tempfile
import unittest
from pathlib import Path

from dotfactory import plan_spec
from dotfactory.cli import _demo_config, _git
from dotfactory.delivery import DeliveryError, latest_check
from dotfactory.instance import FactoryConfig
from dotfactory.lifecycle import FactoryRuntime
from test_verified_delivery import PLAN, ROOT, VERIFY, ApprovedRuntime, EditingRunner

MODEL = '''"""Toy model of the scheduler.

covers: scheduler.py
    queue.py
"""
import unittest
'''
SCHEDULER_PLAN = PLAN.replace("run pinned checks.", "run pinned checks and touch `scheduler.py`.")
FINDING = {"kind": "out_of_scope", "file": "greeting.py",
           "claim": "Adds a French greeting.", "plan": ".factory/plan.md#out-of-scope line 1"}


class SpecRunner(EditingRunner):
    def __init__(self, *, plan=PLAN, model_criterion=False, findings=()):
        super().__init__()
        self.plan, self.model_criterion, self.findings = plan, model_criterion, list(findings)

    def run(self, launch):
        result = super().run(launch)
        root = Path(launch.workspace_path)
        if launch.request.state_id in ("Autoplanning", "Planning"):
            (root / ".factory/plan.md").write_text(self.plan)
            if self.model_criterion:
                path = root / ".factory/verification.json"
                definition = json.loads(path.read_text())
                definition["criteria"][0]["files"].append("tests/test_model.py")
                path.write_text(json.dumps(definition))
        elif launch.request.state_id == "Verifying":
            path = root / ".factory/delivery.json"
            details = json.loads(path.read_text())
            details["spec_findings"] = self.findings
            path.write_text(json.dumps(details))
        _git(root, "add", ".")
        _git(root, "commit", "--allow-empty", "-m", "spec fixture")
        return result


class PlanSpecContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="df-spec-", dir="/tmp")
        self.root = Path(self.temp.name)
        path = _demo_config(self.root)
        repo = self.root / "repository"
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Fixture")
        (repo / ".factory").mkdir()
        (repo / ".factory/verify.py").write_text(VERIFY)
        (repo / "tests").mkdir()
        (repo / "tests/test_model.py").write_text(MODEL)
        (repo / "greeting.py").write_text('def greet():\n    return "hello"\n')
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "pin verifier and model")
        _git(repo, "push", "origin", "main")
        values = json.loads(path.read_text())
        values["workflows"] = {"default": {"path": str(ROOT / "workflows/verified-python.dot")}}
        path.write_text(json.dumps(values))
        self.config = FactoryConfig.load(path)

    def tearDown(self):
        self.temp.cleanup()

    def plan_check(self, runner, key):
        with FactoryRuntime(self.config, runner=runner) as runtime:
            execution = runtime.start_issue("demo", key)
            runtime.step()
            return runtime.ledger.current(execution)["current_state_id"], latest_check(runtime.ledger, execution)

    def test_plan_missing_a_section_is_rejected(self):
        plan = PLAN.split("## Out of scope")[0] + "## Risks\n- None. unchecked\n"
        state, check = self.plan_check(SpecRunner(plan=plan), "SPEC-D1")
        self.assertEqual("Investigating", state)
        self.assertFalse(check["passed"])
        self.assertIn("## Out of scope", check["error"])

    def test_plan_with_every_section_is_accepted(self):
        state, check = self.plan_check(SpecRunner(), "SPEC-D1-OK")
        self.assertTrue(check["passed"], check.get("error"))
        self.assertEqual("Ready", state)
        self.assertEqual({}, check["required_models"])

    def test_plan_touching_scheduler_without_model_criterion_is_rejected(self):
        state, check = self.plan_check(SpecRunner(plan=SCHEDULER_PLAN), "SPEC-F3")
        self.assertEqual("Investigating", state)
        self.assertIn("tests/test_model.py (covers scheduler.py)", check["error"])

    def test_plan_touching_scheduler_with_model_criterion_is_accepted(self):
        state, check = self.plan_check(SpecRunner(plan=SCHEDULER_PLAN, model_criterion=True), "SPEC-F3-OK")
        self.assertTrue(check["passed"], check.get("error"))
        self.assertEqual({"tests/test_model.py": ["scheduler.py"]}, check["required_models"])

    def test_delivery_with_out_of_scope_finding_cannot_complete(self):
        with ApprovedRuntime(self.config, runner=SpecRunner(findings=[FINDING])) as runtime:
            execution = runtime.start_issue("demo", "SPEC-D3")
            runtime.run([execution], until_state="Investigating")
            check = latest_check(runtime.ledger, execution)
            self.assertEqual("Investigating", runtime.ledger.current(execution)["current_state_id"])
        self.assertEqual("python-verification-v2", check["contract"])
        self.assertFalse(check["passed"])
        self.assertEqual("spec_findings", check["failure"]["category"])
        self.assertEqual([FINDING], check["delivery"]["spec_findings"])

    def test_delivery_without_findings_reaches_review(self):
        with ApprovedRuntime(self.config, runner=SpecRunner()) as runtime:
            execution = runtime.start_issue("demo", "SPEC-D3-OK")
            runtime.run([execution], until_state="Review")
            check = latest_check(runtime.ledger, execution)
        self.assertTrue(check["passed"], check.get("error"))
        self.assertEqual([], check["delivery"]["spec_findings"])


class PlanSpecUnitTests(unittest.TestCase):
    def test_sections_need_a_body_and_ignore_code_fences(self):
        self.assertEqual([], plan_spec.missing_sections(PLAN))
        self.assertEqual(["Behavior", "Out of scope", "Risks"], plan_spec.missing_sections(""))
        empty = PLAN.replace("- Other languages and any UI.", "")
        self.assertEqual(["Out of scope"], plan_spec.missing_sections(empty))
        fenced = "```\n## Behavior\nx\n## Out of scope\ny\n## Risks\nz\n```\n"
        self.assertEqual(["Behavior", "Out of scope", "Risks"], plan_spec.missing_sections(fenced))

    def test_frozen_prompts_without_the_contract_are_not_held_to_it(self):
        self.assertFalse(plan_spec.plan_contract("Commit .factory/plan.md with risks."))
        self.assertFalse(plan_spec.verify_contract(None))
        prompts = ROOT / "workflows/prompts"
        self.assertTrue(plan_spec.plan_contract((prompts / "verified-plan.md").read_text()))
        self.assertTrue(plan_spec.verify_contract((prompts / "verified-verify.md").read_text()))

    def test_coverage_matches_whole_path_components_only(self):
        models = {"m.py": ["factory/src/dotfactory/scheduler.py", "factory/src/dotfactory/ledger.py"]}
        for text in ("edit `scheduler.py`", "edit src/dotfactory/scheduler.py",
                     "edit factory/src/dotfactory/scheduler.py:42"):
            with self.subTest(text=text):
                self.assertIn("m.py", plan_spec.required_models(models, plan_spec.planned_paths(text, None)))
        for text in ("edit tests/test_scheduler.py", "edit skills/x/scheduler.py", "edit scheduler.pyc", "scheduler"):
            with self.subTest(text=text):
                self.assertEqual({}, plan_spec.required_models(models, plan_spec.planned_paths(text, None)))
        proposal = {"verification": {"paths": ["factory/src/dotfactory/ledger.py"]}}
        self.assertEqual({"m.py": ["factory/src/dotfactory/ledger.py"]},
                         plan_spec.required_models(models, plan_spec.planned_paths("no paths", proposal)))

    def test_covers_block_parsing(self):
        doc = "Title.\n\ncovers: a.py b.py\n    c.py\nreviewed-at: abc\n  not-a-path.py\n"
        self.assertEqual(["a.py", "b.py", "c.py"], plan_spec.model_coverage(doc))
        self.assertEqual([], plan_spec.model_coverage(None))

    def test_repository_models_cover_existing_files(self):
        models = plan_spec.covering_models(ROOT.parent)
        for model, covered in models.items():
            for name in covered:
                with self.subTest(model=model, path=name):
                    self.assertTrue((ROOT.parent / name).is_file())

    def test_spec_findings_shape(self):
        self.assertEqual([], plan_spec.spec_findings({}, required=False))
        self.assertEqual([FINDING], plan_spec.spec_findings({"spec_findings": [FINDING]}, required=True))
        with self.assertRaisesRegex(DeliveryError, "requires spec_findings"):
            plan_spec.spec_findings({}, required=True)
        for bad in ("none", [dict(FINDING, kind="style")], [dict(FINDING, claim=" ")],
                    [dict(FINDING, extra="x")], [{"kind": "out_of_scope"}]):
            with self.subTest(bad=bad), self.assertRaises(DeliveryError):
                plan_spec.spec_findings({"spec_findings": bad}, required=True)


if __name__ == "__main__":
    unittest.main()
