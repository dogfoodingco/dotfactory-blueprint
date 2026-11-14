## Purpose
Refund totals on the account dashboard stay current.

## Details
- Recompute dashboard totals when a refund event arrives.
- Keep the existing nightly reconciliation job unchanged.

## Behavior
Before: the account dashboard keeps showing the pre-refund total until the nightly reconciliation job runs, so support agents quote stale balances to customers.
After: the account dashboard recomputes the total within one second of each refund event and shows the new balance with a "refunded" badge beside the affected order.

## Out of scope
- Changing how refunds are approved or how the payment provider is called.

## Risks
- Duplicate refund events could double-count a refund; criterion `refund-idempotent` checks it.
