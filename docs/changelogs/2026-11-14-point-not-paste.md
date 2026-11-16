# Handoffs point at plans; Investigating files missing checks

- `work.md` and `verified-{implement,plan,verify}.md` say "Reference plans, ADRs, issues and ledger rows by path or URI; do not paste them." Copied plan text drifts from the frozen plan. `factory/WORKFLOW.md` re-rendered.
- The `Investigating` bullet in `work.md` names a missing check in the outcome as a proposed follow-up issue. The agent does not file it: workers do not contact Linear, and the host publishes the outcome.
- `factory/src/dotfactory/pasted_plan.py`: report-only check for runs of 12+ words shared in order with the frozen `plan.md`. URIs, bare paths, space-free inline code and heading lines are blanked. `python3 -m dotfactory.pasted_plan PLAN TEXT...` exits 1 on a paste. It does not gate a transition.
