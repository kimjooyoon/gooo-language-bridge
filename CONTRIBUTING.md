# Contributing

Choose the path that fits what you observed. English and Korean reports are
welcome. A focused question or small reproducer is enough to start a discussion;
you do not need a finished implementation to propose useful work.
The [experiment catalog](docs/experiments.md) provides browser demos, native
reproducers and semantic bridges to adapt.

## Native observation: no Gooo compiler needed

Run [your first native observation](docs/first-observation.md), then change one
input or operation for your own workflow. The [JavaScript driver](examples/js-differential/README.md)
supports pinned Goja and Sobek sources against Node.js. A `.gooo` file is not
required for native observations, driver fixes or documentation improvements.

If you already have Go test captures, the
[recorded-outcome comparison](examples/go-test-comparison/README.md) can compare
selected cases without rerunning a build. Keep the source/runtime and original
failure context separately; the helper does not authenticate them.

For an already submitted review, the [saved reply check](docs/review-readback.md)
compares its captured body and anchors with the original request. Missing fields
lead to existing comment GETs; a match establishes no permission or freshness.

For an architecture dependent result, the [Go integer parsing example](docs/go-integer-width.md)
shows how to retain a runtime witness, original failure and successful comparison
while preserving the destination type's overflow checks.

Use the [native observation form](https://github.com/kimjooyoon/gooo-language-bridge/issues/new?template=native-observation.yml)
to share the exact engine source, minimal script, relevant runtime identity,
observed/expected values, input bounds and related work. Keep original output
and counterexamples. A difference is a reason to investigate; use the relevant
contract to decide what it means. Do not submit the included known examples as
new upstream bugs.

## Gooo semantic bridge

For a new bridge, open a [bounded bridge proposal](https://github.com/kimjooyoon/gooo-language-bridge/issues/new?template=semantic-bridge.yml)
with an OSS language, pinned source URL and license, observable behavior,
input domain, exclusions and a useful outcome. Its implementation needs an
independently authored `.gooo` activity with stable semantic IDs, a native
reference runner, finite comparisons and preserved failure evidence.
Never translate an entire project before validating a small useful behavior.

Start with [Python floor division](docs/python-go-integer-division.md) or
[string-length units](docs/string-length-units.md). Preserve counterexamples such
as negative operands; do not add only positive examples to raise pass counts.

## Validation and upstream work

Run `python3 -m unittest discover -s tests` and the relevant bounded reproduction.
Gooo source changes also need their native/Gooo comparison. Record which checks
you ran and which scope they cover. Do not describe a skipped test as passing.
CI acceptance requires the exact PR revision, all checks successful, and the
original receipts. No human approval is required by this repository's policy.
Only GitHub rules actually configured enforce that policy. The
[offline bundle audit](docs/audit-ci-evidence.md) checks captured file integrity
and execution context; it does not replace semantic verification or authenticate
the GitHub run by itself.

External PRs must follow each upstream project's contribution policy and solve
a real issue. Record proposed, submitted and accepted contributions separately.
English is the shared documentation language. Issues can still be
opened without a form when neither path fits.
