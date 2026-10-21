# Contribution ledger

The account had 110 followers when `gh api users/kimjooyoon` was observed on
2026-10-22 (Asia/Seoul). The long-term objective is 1,000 followers earned through
useful public contributions. Follower changes alone do not establish causation.
No follow-for-follow, bulk outreach, duplicate PRs or acceptance claims.

## Yaegi operator assignment, ready for review

- Existing report: https://github.com/traefik/yaegi/issues/1736
- Submission: https://github.com/traefik/yaegi/pull/1738
- Original: `fcb76d1ece0c3edc2548c39aa5b170475d2261bb`
- Patch: `6f5190d3aa87b60def588499c3b3577b5019e298`
- Independent author of the issue: `rohanthewiz`; credit the existing report.
- Changes: two interface guards in CFG operator assignment and ten slice cases, three host field/map/pointer cases, and three single discarded-result cases.
- Original: eleven selected storage cases fail (unchanged cells and nil returned pointer);
  the Boolean case additionally panics.
- Fixed: thirteen storage and three single discarded-result cases pass, including targeted race checks; local vet passes.
- Full local suite is not green: CLI cancellation fails on macOS/arm64 Go 1.26.5,
  also reproduced separately on the original revision. The full run was intentionally stopped after about four minutes during
  native/interpreter consistency checks to bound resources; it is not certified green.
- With the canonical GOPATH layout, interpreter-wide `go test -short ./interp`
  and `go test -short -race ./interp` pass (4.6s and 10.6s locally). The initial noncanonical layout also produced import-path failures.
- Wider checks caught a draft regression on blank assignments; it was fixed
  before this final patch revision and three discard cases preserve that boundary.
- Status observed 2026-10-22 (Asia/Seoul): CLA reports success and the unchanged
  patch is ready for review. Upstream Actions still require first-contributor approval.
  The agent did not sign a legal agreement. The submission is not merged.
- AI authorship is disclosed in the PR; upstream review policy remains upstream's.

CI in this repository reproduces the focused before/after evidence. It cannot
authorize merging to an external project. The current Python/Gooo arithmetic
bridge and this Yaegi fix are separate evidence scopes; no Yaegi/Gooo integration
or general language equivalence is claimed.

## Chroma Gooo lexer, submitted

- Upstream: https://github.com/alecthomas/chroma/pull/1410
- Source: `f2224b4a0bd96f64da4cd9a92b293d81aaaf71cd`
- Recent activity: lexer PRs #1404/#1405 merged October 15 and #1407 October 18, 2026 UTC.
- XML lexer, alias/filename discovery, two fixtures (128 tokens), generated registry metadata.
- Both fixtures pass pinned Gooo v0.6.38-dev check. Bodies remain raw strings; no Go body parsing or Gooo runtime dependency.
- Local full tests, lexer/registry race checks, lint and stable metadata generation pass.
- Upstream CI is `action_required` for a first contribution; upstream acceptance is unproven.
- `tools/verify_chroma.py` runs full tests, Gooo fixture race tests and metadata freshness against the exact submission. Its CI proof does not include lint; the lint claim above is local only.
- Fork workflow activation did not start a run during observation. Independent proof therefore runs in this existing workbench's CI, retaining stdout, stderr and file hashes. Fork PRs are not counted as upstream acceptance.
- AI assistance is disclosed in the upstream PR and commit trailer.

## Public entry points, observed 2026-10-22

The [public profile](https://github.com/kimjooyoon) now links the verified
consumer release and this workbench. The existing introduction and project
links were preserved. [Profile commit 1797621](https://github.com/kimjooyoon/kimjooyoon/commit/1797621142f9ce810e3f99cde2fefb46de68b713)
binds the edit; the new links were observed on the rendered profile. The release
manifest hash was checked against the published asset before adding its link.
This establishes a discovery route; it is not evidence of adoption or follower growth.

## Additional Yaegi boundary observation, 2026-10-22

The same patch corrects assignments into a host struct interface field, a host
map interface entry and a host interface pointer. Each new case fails on the
original revision and passes on the patch. Only tests changed upstream.

A separate sequence of mixed-type blank assignments still fails with
`reflect: call of reflect.Value.SetInt on bool Value` on both revisions. The
fixture in `tests/fixtures/yaegi_mixed_blank_test.go` is injected only into the
workbench's temporary checkout and retained as an expected failure in separate
`known-before` / `known-after` logs. It is not counted as a fixed case and is not
added to the upstream passing regression suite.
