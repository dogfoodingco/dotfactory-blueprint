# Prose pattern checks

- `factory/src/dotfactory/prose.py` holds one slop-phrase list: AI vocabulary, copula avoidance, chatbot framing, generic closes, and the narrow negative parallelism forms. Code, short double-quoted phrases and enumerations of three or more listed words are skipped.
- The `plan-result-v2`, `implementation-result-v2` and `python-verification-v2` checks record `prose_warnings` from `plan.md`, `demo.md` and the `delivery.json` summary.
- Warnings never change a receipt's verdict, so there is no state or contract change.
- Tests fail if the Linear run summary templates contain a pattern.
