Inspect the committed change against .factory/plan.md, the issue requirements,
and the latest applicable human feedback. Report spec discrepancies as `spec_findings`
below and return "complete"; report any other discrepancy with preferred_label "failed" and an explanatory outcome.
Keep scope fixed. Ensure .factory/delivery.json describes actual limitations.
Record that inspection in .factory/delivery.json as `spec_findings`, a list
(`[]` when the diff matches the plan) of {"kind", "file", "claim", "plan"} objects.
kind is `unbacked_behavior`
(a `## Behavior` after-state no code or test produces), `unrequested_change`
(changed behavior no plan section asks for) or `out_of_scope` (the diff touches
an `## Out of scope` item); `plan` cites the plan line. Any finding fails the
host check, which routes to Investigating; do not fix the diff here.
Do not modify .factory/verify.py. Commit any report changes and leave a clean tree.
Return preferred_label "complete", an outcome summarizing what happened, and kind verification and local file evidence including
.factory/delivery.json. The factory runs the approved planning revision's verification script
against an isolated export of committed HEAD. Only its passing receipt allows
Review. Do not contact Linear, publish, or merge; the operator exports the packet.

If an approved check needs changing, stop and explain why; do not weaken it.
