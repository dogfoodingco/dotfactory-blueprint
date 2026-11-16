# ADR-0051 Count Linear requests on the coordinator host

- Status: Proposed

## Decision

- Count completed transport attempts by project, GraphQL operation, UTC minute, and outcome. Exclude local cooldown deferrals.
- Coordinators with the same `DOTFACTORY_HOME` share one SQLite aggregate store. Retain 24 hours during active traffic.

## Why

A rate-limit receipt shows which request Linear rejected. Counts show which operations account for the most requests across coordinators.

## Consequences

- The store contains project keys, operation names, and counts. Credentials, queries, and variables stay outside it.
- A failed count write emits a throttled diagnostic. SQLite contention adds at most the configured timeout per busy wait.
- Aggregation is host-local and starts once the coordinators run this code.

## Revisit when

Coordinators need to compare request counts across hosts or local write contention regularly drops counts.

## Evidence

- `factory/tests/test_linear_requests.py`
