# ADR-0051: Reuse project verification maps

- Status: Proposed
- Date: 2026-11-16

## Decision

1. Planning and Verifying read a project's existing verification guide and
   feature map in place, if present. Dotfactory keeps no second catalog.
2. Planning records selected cases, durable effects, prerequisites, non-claims
   and uncovered paths, mapped to acceptance criteria and registered methods.
3. Verifying runs the affected cases within approved scope and carries
   unresolved gaps into `.factory/delivery.json` limitations.
4. Map prose is reference material. It never registers a method, grants
   execution authority or replaces the host receipt.

## Why

- Projects already document how to exercise their features. A copy in
  dotfactory drifts from the project's own recipes.
- Commands in Markdown are not reviewed like registered methods.

## Consequences

- Prompt guidance only: no new workflow state, host check or method type.
- A missing map is setup work, not a passing check.
- Structural validation of maps is left to an optional capability.

## Alternatives

- Duplicate maps in dotfactory: recipes and proof gaps diverge.
- Treat map commands as methods: bypasses method registration and approval.

## Revisit when

- Projects need cases that cannot express durable effects without
  duplicating registered verification methods, or
- missing or stale maps are common enough to need a host check.
