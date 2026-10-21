# Bootstrap observations

On 2026-10-22 (Asia/Seoul), local CPython 3.9.6 and pinned Gooo
v0.6.38-dev with Go 1.27.3 compared the explicit floor-division bridge.
The first attempt used 136 cases and was rejected before execution with
`composition cases require schema and 1..128 cases`.
The bounded domain was reduced to 120 pairs: dividend -7..7 and nonzero
divisor -4..4. The next run reported PASS, 120/120 expected observations.
This is a local observation; GitHub run artifacts are the independently
inspectable CI evidence. There are no submitted or accepted upstream PRs yet.
