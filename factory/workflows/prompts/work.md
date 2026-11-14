Read the repository instructions and work only on the current workflow state.

- `Autoplanning` or `Planning`: inspect the issue and repository, then produce a concrete plan. Do not implement.
- `Implementing` or `Reworking`: implement the requested change and verify the relevant checks.
- `Verifying`: verify the implementation and report evidence; do not broaden the change.
- `Investigating`: diagnose the recorded failure and make only the recovery change the issue requires. If the failure reveals a missing check, name it in your outcome as a proposed follow-up issue whose plan adds it as an automated rule or test; do not file it yourself.

Do not post comments to Linear. The host publishes your result and the next decision; an extra comment is a second inbox notification without a verdict.

Use the immutable execution context below as the task identity. Preserve unrelated work and return evidence URIs for claims you verified. Reference plans, ADRs, issues and ledger rows by path or URI; do not paste them.
