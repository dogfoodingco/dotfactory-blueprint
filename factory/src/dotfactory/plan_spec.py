"""Plans state behavior, scope and risks; Verifying checks the diff against them.

ADR-0112. Presence and shape only: whether a section or a finding is right is
the planner's and verifier's judgement, never this module's.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import Any

REQUIRED_SECTIONS = ("Behavior", "Out of scope", "Risks")
FINDING_KINDS = ("unbacked_behavior", "unrequested_change", "out_of_scope")
FINDING_FIELDS = ("kind", "file", "claim", "plan")
# A frozen prompt that never asked for the contract cannot be held to it.
PLAN_MARKER = "## Out of scope"
VERIFY_MARKER = "spec_findings"
_PATH = re.compile(r"(?<![\w./-])((?:[\w.-]+/)*[\w.-]+\.[A-Za-z]\w*)(?![\w/])")


def _sections(plan: str) -> list[dict[str, Any]]:
    """`#`-`###` headings outside fenced code, each with its lowercased title and body lines."""
    result: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    fence = None
    for line in plan.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            run, suffix = marker.groups()
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not suffix.strip():
                fence = None
        heading = None if (fence or marker) else re.fullmatch(r"#{1,3}\s+(.+?)\s*#*", line)
        if heading:
            current = {"title": heading[1].strip().lower(), "lines": []}
            result.append(current)
            continue
        if current is None:
            current = {"title": "", "lines": []}
            result.append(current)
        current["lines"].append(line)
    return result


def plan_contract(prompt: Any) -> bool:
    return isinstance(prompt, str) and PLAN_MARKER in prompt


def verify_contract(prompt: Any) -> bool:
    return isinstance(prompt, str) and VERIFY_MARKER in prompt


def missing_sections(plan: str) -> list[str]:
    """Required `##` sections that are absent or have no non-blank body line."""
    filled = {item["title"] for item in _sections(plan)
              if any(line.strip() for line in item["lines"])}
    return [name for name in REQUIRED_SECTIONS if name.lower() not in filled]


def model_coverage(docstring: str | None) -> list[str]:
    """Paths after a `covers:` line, continued by indented lines."""
    covered: list[str] = []
    active = False
    for line in (docstring or "").splitlines():
        if line.startswith("covers:"):
            active = True
            line = line[len("covers:"):]
        elif not (active and line[:1].isspace() and line.strip()):
            active = False
            continue
        covered += line.split()
    return covered


def covering_models(root: Path) -> dict[str, list[str]]:
    """Committed test models under a tests/ directory and the files each covers."""
    from .delivery import DeliveryError, git
    result = subprocess.run(["git", "-C", str(root), "grep", "-l", "-z", "-e", "^covers:", "HEAD", "--", "*.py"],
                            capture_output=True, timeout=15)
    if result.returncode not in (0, 1):  # 1 means no file matched
        raise DeliveryError("cannot discover model coverage in committed tests")
    models = {}
    for entry in result.stdout.decode().split("\0"):
        name = entry.split(":", 1)[1] if entry.startswith("HEAD:") else entry
        if not name or "tests" not in name.split("/")[:-1]:
            continue
        source = git(root, "show", f"HEAD:{name}").decode()
        covered = model_coverage(ast.get_docstring(ast.parse(source)))
        if covered:
            models[name] = covered
    return models


def planned_paths(plan: str, proposal: Any) -> set[str]:
    """Paths the plan names, plus the methods proposal's declared source paths."""
    paths = set(_PATH.findall(plan))
    declared = (proposal or {}).get("verification") if isinstance(proposal, dict) else None
    if isinstance(declared, dict) and isinstance(declared.get("paths"), list):
        paths.update(item for item in declared["paths"] if isinstance(item, str))
    return paths


def _touches(covered: str, named: str) -> bool:
    return named == covered or covered.endswith("/" + named)


def required_models(models: dict[str, list[str]], paths: set[str]) -> dict[str, list[str]]:
    return {model: sorted({c for c in covered for p in paths if _touches(c, p)})
            for model, covered in models.items()
            if any(_touches(c, p) for c in covered for p in paths)}


def require_models(root: Path, plan: str, proposal: Any, definition: dict[str, Any]) -> dict[str, list[str]]:
    """Reject a plan naming a model-covered file unless an automated criterion runs that model."""
    from .delivery import DeliveryError
    required = required_models(covering_models(root), planned_paths(plan, proposal))
    selected = {name for item in definition.get("criteria", [])
                if item.get("kind") == "automated" for name in item.get("files", [])}
    missing = sorted(model for model in required if model not in selected)
    if missing:
        raise DeliveryError(
            "plan touches model-covered files; add an automated criterion listing "
            + ", ".join(f"{model} (covers {', '.join(required[model])})" for model in missing))
    return required


def spec_findings(details: dict[str, Any], *, required: bool) -> list[dict[str, str]]:
    """Validate the verifier's spec findings; absence is allowed only for old prompts."""
    from .delivery import DeliveryError
    if "spec_findings" not in details:
        if required:
            raise DeliveryError("delivery.json requires spec_findings (use [] when the diff matches the plan)")
        return []
    findings = details["spec_findings"]
    if not isinstance(findings, list) or len(findings) > 64:
        raise DeliveryError("spec_findings must be a list of at most 64 findings")
    for item in findings:
        if (not isinstance(item, dict) or set(item) != set(FINDING_FIELDS)
                or item["kind"] not in FINDING_KINDS
                or any(not isinstance(item[key], str) or not item[key].strip() for key in FINDING_FIELDS)):
            raise DeliveryError("each spec finding requires kind (" + ", ".join(FINDING_KINDS)
                                + ") and nonempty file, claim and plan strings")
    return findings
