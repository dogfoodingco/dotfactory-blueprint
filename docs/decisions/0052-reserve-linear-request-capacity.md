# ADR-0052 Reserve Linear request capacity

- Status: Proposed

## Decision

- Meter requests before transport using one host-local budget per Linear endpoint and app identity. Clients without a configured actor share by credential, as with the existing cooldown.
- Defer background requests below 20 percent capacity. Preflight and reads for existing controls can use the reserve down to 2 percent. A native planning reply can use the rest when it reaches the head of its ordered activity queue.
- Refill the estimated budget at the hourly rate and reconcile downward against provider request headers. Provider Retry-After applies at every priority.

## Why

Background projection and repeated polling can consume the shared quota before an operator can pause or stop a run.

## Consequences

- Budget reservations are atomic across coordinators using the same Dotfactory home. The owner-only database stores scope hashes, counters, and timestamps under `linear-budget/requests.sqlite3`.
- The estimate accounts for requests admitted in parallel. A local deferral spends no provider request and keeps retryable work pending.
- External clients and other provider quotas can still trigger cooldown.

## Revisit when

Command reads routinely reach the reserve floor, or the same app identity needs to share its reserve across hosts.

## Evidence

- `factory/tests/test_linear_request_budget.py`
