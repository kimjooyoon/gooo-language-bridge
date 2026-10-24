# Preserve repository context when preparing a contribution response

A synthetic discovery should be described as synthetic. A participant's useful
suggestion is not API approval, and a focused test pass does not clear an
unrelated baseline failure. This B2 planner keeps those distinctions in a
response plan, addressing the overstatement and duplicate-follow-up failures
recorded in [issue #33](https://github.com/kimjooyoon/gooo-language-bridge/issues/33).
It cannot decide whether an unsolicited contribution is useful to a maintainer.

```sh
python3 tools/plan_profile_response.py --gooo .bin/gooo
```

The bounded example first runs the unchanged [B1 planner](contribution-response-planning.md)
and then `urn:gooo:contribution:profile-plan` using Gooo v0.6.38-dev. Both actual
receipts are compared with independent Python references, including input types,
case domain, activity identity, case/workspace digests and every delivery.
Python extracts observations; Gooo expresses the decision order. No network,
model, native fixture execution, posting or recurring work is added.

## Sources and authority

The six profiles in [profiles/](../bridges/contribution-profiles/profiles/) are
bounded source snapshots observed on **24 October 2026 at 23:25:40 UTC**. They
record source URLs, source-byte SHA-256 when captured, separate commit/blob
identities for pinned policy documents, comment IDs, author associations and
observation dates. A repository commit date is not a policy's original
publication date; unknown publication dates remain null. The loader checks
repository/commit/comment URL bindings and criterion source kinds. Hashes bind
bytes and identities; they do not authenticate a source's truth or authority.

| Profile | Recorded evidence | Boundary |
| --- | --- | --- |
| HCL | Contributor intake feedback on PR 815 | Not a formal policy or an explanation of moderation cause |
| Starlark | Collaborator request for clarity and a separate participant's API question | Shortening changes presentation, not language semantics |
| pflag | Collaborator question about discovery origin and practical need | Agent discovery is not a production incident or frequency estimate |
| go-git | PR author's narrow fix acknowledgement; pinned AI policy | Fixed finding and base-existing limitation stay separate; disclosure alone is insufficient |
| Koanf | Collaborator's complete default-hook suggestion | Adaptation is not maintainer API approval |
| agentlanguages | Owner's catalogue feedback; pinned contribution guide | Current guide recommendations do not replace immutable fixture pins |

Each profile distinguishes `published_policy`, `direct_feedback` and our
`inference` sources. Criteria link to sources of the matching kind. GitHub's
`CONTRIBUTOR` and `COLLABORATOR` associations are retained verbatim; neither is
automatically a maintainer designation. Our editorial defaults recommend a
bounded result, minimal example and one useful action. They are adjustable
interpretations, not upstream rules, personality labels or acceptance scores.
Missing one CONTRIBUTING path does not establish that no policy exists.

The go-git profile checks only the recorded understanding/disclosure
prerequisites. It does not implement every AI-policy obligation. A public draft
with unestablished personal understanding has no public-response effect; a
synthetic attestation cannot supply a person's understanding. This is a bounded
system outcome, not a new human approval workflow or a universal AI ban.

## Contracts and decisions

The new schemas are separate from the producer contract:

| Schema | Purpose |
| --- | --- |
| `gooo/contribution-profile/v1` | Sourced repository snapshot and editorial interpretation |
| `gooo/contribution-context/v1` | Supplied interaction, policy-discovery and scope observations |
| `claim-assertion.schema.json` | A typed assertion bound to a B1 claim ID, embedded in the versioned input |
| `gooo/profile-response-input/v1` | Complete B1 packet plus context, assertions and profile reference |
| `gooo/profile-response-result/v1` | Complete input, B1 result, profile snapshot, digests and `effect: none` |

The JSON files in [contribution-profiles/](../bridges/contribution-profiles/)
define exact fields, bounds and enums. The producer `gooo/contribution-evidence/v1`
and B1 input/result schemas and Gooo source remain byte-identical to accepted
B1 revision `6142c05e9aa32b5003dcd77cfbc87669f66ed402`. Tests pin all four hashes.
Ports P1 owns its real evidence exporter; this change neither substitutes a
synthetic packet for that artifact nor counts a new producer integration.

The profile reference binds the exact profile file bytes and repository.
Unknown categories remain provisional. The result binds canonical input bytes,
profile bytes and the Gooo decision source; changing a profile requires a new
reference. `profile_as_of` and its bounded age allowance govern the supplied
profile snapshot separately from B1's supplied conversation freshness. Neither
clock is a live policy check. B1 refusals and stale evidence keep precedence;
subsequent checks cover profile/claim binding, profile age, confirmed interaction
restrictions, policy discovery, external prerequisites and posted-but-unaccepted
clarifications. A restriction does not trigger use of an alternate channel.

Readable `maintainer` and `internal` views project the same result. They lead
with an implication and one next action, then retain claim IDs/statuses, roles,
context, evidence, failures, uncertainty and exclusions. Source text is quoted
as data. Audience and brevity never upgrade evidence or create an effect.
This is a deterministic planning projection, not a prose-quality validator,
publication permission, policy-compliance certificate or acceptance prediction.

## Exact example coverage

All inputs are explicitly **synthetic planning fixtures**. Linked public
observations provide historical context; they are not fresh upstream state.
The 24 October profile snapshots are applied to frozen hypothetical inputs,
some dated 22 October. That does not establish what policy applied on 22 October.
The Goja supplement describes the historical unimplemented state, not the later
PR 825. The vendor supplement retains a reported source assessment with no
runtime execution; private mail bodies are not published.

The denominator is **16 original scenarios**, separately **2 supplemental
scenarios**, and separately **6 protocol counterexamples**. All 24 pass through
both real Gooo activities. Original scenarios cover HCL roles/moderation/composer
state, duplicate confirmation, synthetic pflag discovery, go-git fix/baseline
separation, Koanf suggestions, posted Starlark clarification, partial policy
discovery, external prerequisites, unfamiliar categories, API questions,
catalogue pins, restrictions, freshness and focused/baseline/hosted-CI scope.
Counterexamples reject a wrong profile digest, invented production incident,
stale profile, participant API approval, all-tests claim and invented hosted pass.
These counts measure fixture coverage, not real-world usefulness or acceptance.

Each invocation retains a new `evidence/contribution-profiles/attempt-*/`
directory with both executions, individual results, two views per result,
inputs and `attempt-manifest.json`. The root summary hashes all retained attempts
and source dependencies. Eight attempts bound the layout; use a fresh evidence
checkout after that limit. CI adds one invocation to the existing single
12-minute job and integrity inventory `contribution-profiles-17`. The auditor
retains strict older-source inventory checks and rejects reserved nested
summary/report filenames. B3 still requires real producer integration; the
candidate collector's separate preservation work remains pending before its
next live scan.
