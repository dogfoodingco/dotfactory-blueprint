# Plan brief and spec findings

- `plan-result-v2` plans must have nonempty `## Behavior`, `## Out of scope` and `## Risks` sections.
- A plan naming a file listed in a test's `covers:` docstring must select that test as an automated criterion.
- `.factory/delivery.json` requires `spec_findings`. Any finding fails Verifying and routes it to Investigating.
- The checks apply only when the frozen prompt carries the contract, so earlier runs keep their old contract. They verify presence and shape only. See ADR-0112.
