# Contribution ledger

These are dated submission notes. Use the [experiment catalog](experiments.md)
to find reusable cases and the [continuing evidence record](https://github.com/kimjooyoon/gooo-language-bridge/issues/24)
for newer observations. Check each upstream PR for its current state.

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

## Chroma prefixed Go imaginary literals, submitted

- Upstream: https://github.com/alecthomas/chroma/pull/1411
- Original: `ef614fb8afe8ccf3f2b2cb45117c543a3ce8832b`.
- Patch: `9eeba90bf714797853d60a5e815f8db33c00ae35`.
- Recent maintainer merges: #1387/#1393 improved Go numeric forms; #1407 merged
  October 18. Searches found no existing prefixed-imaginary patch before submission.
- Four Go lexer rules preserve `i` in binary, octal, hexadecimal and hexadecimal-float
  imaginary tokens, consistent with decimal imaginary classification.
- New fixture: eleven corrected forms and seven unchanged decimal/non-imaginary
  controls. All eighteen expressions compile in native Go; its scanner emits one
  `IMAG` token for each affected literal. The fixture fails on the unchanged base.
- Local full Chroma tests, Go fixture race tests and pinned lint pass on macOS
  arm64. No existing fixture changes, metadata changes or Gooo dependency.
- `tools/verify_chroma_go_numbers.py` retains original/patch token observations,
  native compilation, the failing/passing regression, targeted race and full tests.
  Independent CI does not replace upstream approval; no acceptance is claimed.
- AI authorship is disclosed in the upstream PR and commit trailer.

The [Go specification](https://go.dev/ref/spec#Imaginary_literals) permits these
forms. This is a lexical classification fix, not complex-number evaluation in
Gooo or a general Go lexer correctness proof.

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

## Bubbles forward Delete, submitted

- Report: https://github.com/charmbracelet/bubbles/issues/1071
- Submission: https://github.com/charmbracelet/bubbles/pull/1072
- Original: `c3bde0d166c2ca607d9864493453fd77bdcae7e4`.
- Patch: `c328d151ef791e224ebff53d664fbfa7586796fe`.
- A three-line reorder prevents a Delete press from removing the line's final
  character and also merging the next line. Existing line-end joining remains.
- Three original failures become eight patched passes; five boundary controls
  remain equal. The independently executed Gooo edit matches all eight.
- Local Go 1.26.0 full tests, textarea race tests, build, vet and pinned
  golangci-lint v2.13.1 pass. The eight-case regression also passes on Go 1.27.3.
- `tools/verify_bubbles_delete.py` fetches exact sources and retains original
  focused/race test events, native inputs, source hashes and the Gooo receipt.
  Its CI scope is focused reproduction, not the full local checks above.
- Upstream workflows require approval at submission; acceptance remains unproven.
  AI assistance is disclosed. No Gooo runtime dependency is added to Bubbles.

Read [One Delete press should perform one edit](delete-forward-newline.md) for
cursor units, the complete eight-input table and reproduction instructions.

## urfave/cli completion groups, submitted

- Upstream: https://github.com/urfave/cli/pull/2485
- Original: `10f69fd3c38de86a3bc17810dcb7f818b494f027`.
- Patch: `5dbdb1037281c390c4f98c144ab82150262bdff9`.
- Ten implementation lines preserve pending grouped tokens for completion
  callbacks. Normal execution errors and complete/empty values keep their behavior.
- Local upstream regression: nine original failures become 20 patched passes,
  including root/child/nested scope and ASCII/Unicode names. Full/native race,
  no-template tests, vet, API/binary-size checks, README example and lint pass.
- Upstream test run 39697751487 passes six Linux/macOS/Windows × stable/oldstable
  jobs; lint run 39697751464 passes on the exact patch head. Submission remains open
  at this observation; no maintainer review or acceptance is inferred.
- `tools/verify_cli_completion.py` independently observes 20 native cases on both
  sources and on the patched race run, then compares the Gooo intent activity.
  There are 12 distinct policy inputs: native command depth is outside the activity.
- The activity takes a corpus-declared incompleteness classification; it does not
  classify arbitrary tokens or reimplement the parser. The verifier retains exact
  native arguments, callback/action/error records, source hashes and Gooo receipt.
- Codex authorship is disclosed upstream. No Gooo dependency is added upstream.

Read [An unfinished flag is useful input during completion](completion-input-intent.md)
for the concrete counterexamples, context boundary, reproduction and exclusions.
