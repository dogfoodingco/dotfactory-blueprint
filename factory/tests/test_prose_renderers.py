"""Host-written Linear text must not contain shared slop patterns.

Agents never author these renderers, so a match is a template defect: the tests
fail rather than warn. Fixture inputs are clean, so any match comes from a template.
"""
import ast
import importlib.util
import inspect
import tempfile
import unittest
from pathlib import Path

from dotfactory import ObservationService, linear_evidence, prose
import test_linear_evidence as evidence_fixture

RENDERERS = (linear_evidence,)


def slop(text):
    return [(item.pattern, item.text) for item in prose.scan(text)]


def template_literals(source):
    """Every string constant in module source except docstrings."""
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]


def patched(module, old, new, directory):
    """A private copy of ``module`` with one template literal edited, loaded from ``directory``."""
    source = inspect.getsource(module)
    if old not in source:
        raise AssertionError(f"template literal {old!r} not found in {module.__name__}")
    path = Path(directory) / (module.__name__.rsplit(".", 1)[1] + "_injected.py")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(module.__name__ + "_injected", path)
    copy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(copy)
    return copy


class TemplateLiteralTests(unittest.TestCase):
    def test_renderer_literals_are_clean(self):
        for module in RENDERERS:
            with self.subTest(module=module.__name__):
                self.assertEqual([], slop("\n".join(template_literals(inspect.getsource(module)))))

    def test_injected_literal_is_caught(self):
        source = inspect.getsource(linear_evidence).replace("'Currently'", "'I hope this helps'", 1)
        self.assertEqual([("chatbot-frame", "I hope this helps")], slop("\n".join(template_literals(source))))


class LinearSummaryTests(unittest.TestCase):
    setUp = evidence_fixture.LinearEvidenceTests.setUp
    tearDown = evidence_fixture.LinearEvidenceTests.tearDown

    def render(self, render):
        snapshot = self.ledger.run_snapshot(self.execution)
        projection = ObservationService(self.ledger, self.kernel).execution_projection(self.execution)
        return render(snapshot, projection, self.ledger.run_history(self.execution))[0]

    def test_summary_is_clean_and_fails_when_a_pattern_is_injected(self):
        self.assertEqual([], slop(self.render(linear_evidence.render_linear_run_summary)))
        with tempfile.TemporaryDirectory() as directory:
            copy = patched(linear_evidence, "'Completed' if completed else 'Currently'",
                           "'Completed' if completed else 'Currently, and seamlessly,'", directory)
            injected = self.render(copy.render_linear_run_summary)
        self.assertIn(("ai-vocabulary", "seamlessly"), slop(injected))


if __name__ == "__main__":
    unittest.main()
