# Bound claims before preparing a response

The planner separates a useful response from another unsolicited confirmation.
It retains the actor's actual observed role, compared revisions, test scope,
uncertainty and failures. A readable view projects those same supplied claims;
it does not become evidence that they are true or grant posting authority.

This is **B1 of [issue #33](https://github.com/kimjooyoon/gooo-language-bridge/issues/33)**.
It implements original scenarios **1, 2, 3, 4, 6 and 15**, plus three refusal or
external-precondition packets. All nine packets are synthetic offline fixtures.
The remaining original scenarios, six sourced profiles and supplemental cases
are covered by the separate [B2 profile planner](contribution-profile-planning.md).
The [B3 consumer](producer-response.md) integrates the published real P1 export. Earlier 28 October pause
dates were superseded by the maintainer's return and explicit 25 October restart.

## Run the bounded example

```sh
python3 tools/plan_response.py --gooo .bin/gooo
```

The current pinned compiler runs a separate `Plan` activity. Its actual deliveries
are checked against an independent Python reference for the exact inputs, case
domain, semantic activity ID, cases digest and workspace digest. Results and
readable views are retained in `evidence/response-planning/attempt-*/`; the root
summary binds all retained attempt files. An invocation never replaces an older
attempt's diagnostics. Per-attempt records use `attempt-manifest.json`; only the
root `summary.json` participates in the required summary inventory. Eight retained attempts bound the layout; use a fresh
evidence checkout after that limit. CI uses one attempt in the existing single
12-minute job. There are no API/model calls, native fixture reruns or posts.

The HCL packets preserve a `COMMENTED` review minimized as `low-quality`, an
unlocked PR, historical composer unavailability and a later editable composer.
They retain unknown moderation cause and permission. Visibility is not a
successful submission or proof of an unblock. An asserted PR-author role on
the observed reviewer is refused. Duplicate confirmation yields `NO_POST`.

The go-git packet separates a fixed original finding from another mismatch also
present on the base. The `111...`/`222...` revisions and `fixture-version` are
**synthetic identifiers**, not replayed Git revisions. Their public source link
provides historical context only. A changed head/feedback yields
`NEEDS_CURRENT_EVIDENCE`; missing base comparison or a misbound revision refuses
the claim. An unknown human-understanding requirement produces a no-publication
system result, without fabricating a person's participation or an approval lane.

## Versioned producer contract

[evidence.schema.json](../bridges/contribution-response/evidence.schema.json)
defines **`gooo/contribution-evidence/v1`**, the independent input for ports P1.
One record contains these fields; the JSON Schema is authoritative for exact
keys, types, enums and bounds:

| Field | Meaning |
| --- | --- |
| `id`, `origin` | Stable record ID and synthetic/frozen/producer observation origin |
| `identities` | Separate source commit, source blob, base, candidate and reference name/version/commit |
| `execution` | Observed phase/outcome, tested scope, comparison mode and separate base/candidate outcomes |
| `references` | Stable reference IDs, artifact/source URLs or locators, and digest when actually known |
| `uncertainty`, `failures`, `exclusions` | Material limits retained in both machine and readable outputs |

Identity and reference digest `null` means unknown. Explicit `unknown` execution
phase/outcomes stay distinct from `not_executed` and `not_compared`; parse or
compile success cannot support a successful behavior-test claim. `comparison: not_compared`
and the separate outcome enum mean no comparison was observed; absence never
becomes a pass. Blob and commit fields are distinct. File hashes refer to actual
bytes only when the producer observed them; a public link is not an attestation.
The record contains **no actor, tone, policy or posting decision**. P1 owns its
adapter and verification against its existing native-shard artifact; B1 does not
guess that artifact's meaning or count a new consumer before integration.

Consumer review by ports P1 identified observation stages that cannot be called
tests: `native_execution`, `oracle_comparison`, `saved_replay` and
`input_observation` are preserved as separate phase values. `observed`,
`cancelled`, `incomplete` and `partial` remain distinct outcomes (also available
for each comparison arm). A producer records any normalization from its raw
reader vocabulary explicitly, retaining the original typed facts through hashed
references; an `OBSERVED` record must not become `targeted_tests/pass`.
These observations do not satisfy the planner's fixed-finding test preconditions.
The readable view keeps unfinished states visible, with no completed-pass claim.

[input.schema.json](../bridges/contribution-response/input.schema.json) wraps
these records in **`gooo/contribution-response-input/v1`**: actor and asserted
claim roles, contribution phase, sourced policy identity/basis, interaction
snapshot, bounded freshness observations, explicit usefulness observations and
claims referencing evidence IDs. All nullable/unknown fields remain explicit.
`as_of` is supplied so frozen examples are deterministic; it is not a live
freshness check. A collector must establish a current snapshot independently.
The bounded validator implements only the fixed schemas' JSON Schema subset;
it rejects extra keys, duplicate IDs/JSON keys and unsupported versions.

The six Boolean planning observations are derived and source-bound separately
from the old candidate check. They express role consistency, evidence binding,
supported comparisons, freshness, external prerequisites and useful addition.
Their truth is **not** independently established by copying a value into a
packet. In particular, `requested`/`adds_information` and policy satisfaction
are supplied observations, not an automatic usefulness or legal judgment.

## Decision and readable projection

The stable activity `urn:gooo:contribution:response-plan` checks roles, binding
and comparison first, then freshness, external prerequisites and usefulness.
Its outcomes are `REFUSED_INVALID_CLAIMS`, `NEEDS_CURRENT_EVIDENCE`,
`EXTERNAL_REQUIREMENT_UNSATISFIED`, `NO_POST` or `BOUNDED_DRAFT_READY`.
There is no acceptance prediction, publishing effect or human sign-off result.

[result.schema.json](../bridges/contribution-response/result.schema.json) defines
**`gooo/contribution-response-result/v1`**. It retains the complete input packet,
canonical input digest, planner-source digest, decision/reason and `effect: none`.
The deterministic renderer checks those bindings, leads with the result and
practical implication, provides one next action and retains all claim IDs,
statuses, uncertainty, failures and exclusions in its appendix. A refused or
stale claim is not presented as a current fix. Rendering the same result twice
has no second effect. Free-text limitations are supplied data, not semantically
verified advice or a new authority source.

The five observations and 32 offline cases in
[the candidate check](contribution-candidate-check.md) are unchanged. Its live
collector's [live-attempt preservation](contribution-candidate-check.md#live-collection-preserves-earlier-evidence)
is implemented separately. B1 adds no acquisition changes, posting automation, six-profile
completion, ports exporter or engine work. Required CI now includes and audits
this planner's evidence. Its original inventory was `response-planning-16`;
B2 extends it to `contribution-profiles-17`. Older inventories remain valid only
against their corresponding original source.
