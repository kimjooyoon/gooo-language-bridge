# Roadmap

1. Deliver one bounded Python arithmetic bridge with independent observations.
2. Add a counterexample corpus and separate selection/evaluation inputs when
   construction choices are introduced. Current explicit body has no model search.
3. Compare named UTF-8 byte, Unicode code-point and UTF-16 unit counts using
   independent Go/Python operations; preserve the bounded scalar-string domain
   and licensing provenance. Do not treat shared spelling such as `len` as a
   shared semantic unit. A JavaScript runtime remains outside the current scope.
4. Find a concrete upstream test/documentation gap before submitting a contribution.
5. Measure case count, wall time and required manual repair separately. No star
   target, theoretical performance claim or contribution count substitutes for evidence.

Resource policy: one Linux CI job, 12-minute limit, cancellation of superseded
branch runs, cached pinned compiler, 7-day evidence retention, no scheduled runs.
Avoid matrices and LLM calls until a demonstrated requirement justifies them.
