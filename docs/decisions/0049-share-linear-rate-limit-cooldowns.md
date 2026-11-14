# ADR-0049 Share Linear rate-limit cooldowns

- Status: Proposed

## Decision

- Share cooldowns across Linear clients that use the same endpoint and configured app identity in one Dotfactory home. A client without a configured actor shares with clients that use the same credential.
- Defer requests at the HTTP boundary until Linear's `Retry-After` deadline. Without a usable deadline, wait at least 30 seconds and respect an identifiable exhausted quota's reset time.
- Retain a bounded host-local history of operation names, project keys, quota counters, and retry times. Leave the exhausted quota unknown when response headers do not identify it.
- Let supervised work expose the local control socket during startup backoff. Resume discovery after live preflight succeeds.

## Why

Each coordinator has its own ledger. Repeated polling from separate processes can exhaust the same Linear app quota.

## Consequences

- Cooldowns survive restarts. Requests already sent can still complete.
- An operation-specific throttle temporarily defers other requests on the same identity.
- Coordinators in different homes do not share the backoff.

## Revisit when

One app identity routinely runs across hosts or operation-specific limits regularly delay unrelated work.

## Evidence

- `factory/tests/test_linear_rate_limit.py`
