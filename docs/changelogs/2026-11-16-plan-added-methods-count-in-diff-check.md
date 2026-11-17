# Plan-added methods count in the diff check

- `assert_coverage` passes the reviewed plan's methods and waivers when it re-resolves the real diff. Before, a plan that added a registered method no project rule selects was blocked right after approval, because the diff check demanded evidence the plan already supplied.
- A method the diff needs and the plan neither selected nor waived still fails.
- Not covered by a test: a human-waived method that the real diff no longer selects. The same line credits it.
