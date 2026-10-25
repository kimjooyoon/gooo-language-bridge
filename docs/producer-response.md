# Read real saved producer evidence without upgrading its claims

**Local integration review; P1 source acceptance and public frozen bytes are
still pending.** This document describes the consumer being verified for B3 of
[issue #33](https://github.com/kimjooyoon/gooo-language-bridge/issues/33). It is
not a completed integration or publication-acceptance record.

The P1 export supplies three records from real saved HeaderAddition observations:
`native_execution`, `oracle_comparison` and `saved_replay`. The selected domain
has **50 cases in seven batches**, with **14 execute/replay references**. P1
reports inspecting **82 suites** before selection; the consumer does not rerun
that whole reader. These are different units and scopes.

The existing B1/B2 Gooo activities plan a response over the same complete
records. The supplied internal-review context currently produces
`NEEDS_CONTEXT:POLICY_DISCOVERY`: the six repository profiles do not establish
a policy for this technical producer. The underlying B1 result preserves its
unknown external prerequisite. The result has `effect: none`; missing context
does not create a human approval lane, personal attestation or posting effect.

## Run the local review

```sh
python3 tools/consume_producer_evidence.py --gooo .bin/gooo
```

The default fixture is the real frozen local P1 handoff. It is not the rejected
13-row smoke data or a new synthetic producer run. A different directory requires
an explicit manifest digest and matching supplied review context:

```sh
python3 tools/consume_producer_evidence.py --gooo .bin/gooo \
  --bundle /absolute/path/to/export \
  --manifest-sha256 FULL_SHA256 \
  --context /absolute/path/to/review-context.json
```

This consumer supports the fixed HeaderAddition export envelope, not arbitrary
native evidence formats. It reads only the six named regular files, checks the
external manifest digest and all payload sizes/hashes, validates the unchanged
`gooo/contribution-evidence/v1` schema pin, and checks selected case/reference
domains and replay parents. JSON is parsed from the exact captured bytes;
duplicate keys, nonfinite values, symlinks and unexpected files are refused.
Each file is bounded to 128 KiB and the complete input to 256 KiB.

P1 owns the full native reader and export semantics. The consumer checks the
envelope, bindings and declared facts; it does not independently re-establish
the native executions, Go oracle or full population. The Gooo compiler runs
only the two planning activities. There is no producer native rerun, new model
call, live GitHub collection or automatic publication.

## Keep the observation boundaries

The record identities for source/blob/base/candidate/reference commits are
**null**. Reported Git revisions in the appendix remain reported metadata;
copying them into those identity fields would invent authentication. The
consumer therefore keeps `tested_revision: null` on its bounded observations.
Both `producer_authenticated` and `native_acceptance` remain false even if the
exporter's separate CI succeeds.

Each saved phase's own outcome is retained exactly. Its `pass` describes that
recorded stage, not a newly executed test or whole-run success. All comparison
arms remain `not_compared`, so the records cannot support an original-finding
fix or regression comparison. The original `join` failure,
`command deadline: header-host-consumer`, stays visible alongside the selected
saved observations. No claim is changed to `resolved`.

The actor, timestamps, usefulness and workflow policy in
[review-context.json](../bridges/producer-response/review-context.json) are
explicit internal-review inputs, not producer-authenticated observations of a
current upstream conversation. Frozen `as_of` values make the example stable;
they do not perform a live freshness check. Repository/manifest substitution
or prepopulated producer claims in that template is refused.

## Inspect the result

Every invocation retains a new `evidence/producer-response/attempt-*/` directory:

- `source/` keeps all six original producer files byte-for-byte.
- `context.json` and `input.json` keep the supplied context and constructed packet.
- Base/profile cases and execution receipts bind each actual Gooo delivery.
- `result.json` keeps the complete B2 input, B1 result, producer records, source
  file hashes and reported producer scope/failure.
- `response.md` gives the selected scope, one example, claim IDs/statuses,
  material limits and one next action. Links lead to the full `plan-detail.txt`,
  machine result, source appendix and original technical preview.
- `attempt-manifest.json` and the root summary bind current and retained
  diagnostics. A later invocation does not delete earlier attempts.

Eight attempt paths bound the output. The required CI command adds
`--require-published-source`; it refuses acceptance while the P1 source/CI and
frozen asset pins are pending. This is a source-owned evidence precondition,
not a request for human sign-off. These offline pins do not independently
authenticate GitHub metadata or make an unsigned producer authenticated.

CI adds this small consumer to the existing single 12-minute job and requires
inventory `producer-response-18`. Earlier 13–17 inventories remain valid only
against their corresponding source commits. B1's producer/input/result schemas
and Gooo source remain unchanged. The original producer snapshot notices are
retained under [upstream-licenses/](../bridges/producer-response/upstream-licenses/);
the consumer is independently authored MIT code, and the source snapshot retains
its BSD-3-Clause attribution.
