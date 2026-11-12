# ADR-0112: Check the diff against the plan brief

- Status: Proposed
- Date: 2026-11-12

## Decision

1. **Plan contract.** Every `plan-result-v2` plan has nonempty `## Behavior`,
   `## Out of scope` and `## Risks` sections. The host checks presence only.
2. **Model criteria.** A test whose module docstring has a `covers:` block is a
   model of those files. A plan whose text, or whose methods proposal
   `verification.paths`, names a covered file must list that model in an
   automated criterion's `files`.
3. **Verifying output.** `.factory/delivery.json` carries `spec_findings`:
   `{kind, file, claim, plan}` with kind `unbacked_behavior`,
   `unrequested_change` or `out_of_scope`. A non-empty list fails the
   `python-verification-v2` host check (`failure.category: spec_findings`),
   which routes Verifying to Investigating on the existing `failed` edge.
4. Rules 1–2 and the presence of `spec_findings` apply only when the frozen
   state prompt asks for them. A non-empty list fails regardless.

Code: `factory/src/dotfactory/plan_spec.py`.

## Why

- Scope and risks were optional prose, so Verifying had nothing structured to
  compare the diff with, and its discrepancies arrived as free text.
- A model test proves a property only when it runs; Planning could change a
  covered file without selecting it.
- Workflow prompts are frozen per run; holding an in-flight run to a contract
  its prompt never stated would wedge it in Investigating.

## Consequences

- Presence checks do not judge section quality. Spec findings are agent
  judgements and can be wrong in both directions; the host checks shape only.
- Path discovery is textual: a covered file named only under `## Out of scope`
  still requires the model. Over-selection costs one extra test run.
- A finding cannot be overridden in Verifying; Investigating decides whether
  to rework, replan or correct the finding.
- PlanReview presentation is unchanged; the sections appear in the full plan.

## Alternatives

- Requiring the sections only for Linear-planned runs: the gap is in every
  planned delivery.
- A new required `## Changed paths` section: adds a fourth section; named paths
  plus `verification.paths` suffice.
- Scoring findings in the host: whether a diff leaves scope needs judgement.

## Revisit when

- False findings send more than one in five deliveries to Investigating, or
- a plan changes a covered file without naming it and the model is skipped.
