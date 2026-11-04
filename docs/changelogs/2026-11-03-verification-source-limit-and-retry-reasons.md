# Verification source limit and retry reasons

- Committed verification source is bounded to 16 MiB (was 4 MiB); verification output stays 4 MiB.
- A control `retry` from a human state records its `reason` as `operator_resolution` feedback, so the next attempt's handoff shows what the operator changed.
