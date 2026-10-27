# Gooo Language Bridge

Read Gooo source with syntax highlighting, then explore small comparisons with
other language runtimes.

## Highlight a Gooo file

Requires **Go 1.25+** and network access to fetch Go modules. Download the
[floor.gooo sample](https://github.com/kimjooyoon/gooo-language-bridge/releases/download/examples/highlight-gooo/v0.1.1/floor.gooo)
into your current directory, then run:

```sh
go run github.com/kimjooyoon/gooo-language-bridge/examples/highlight-gooo@v0.1.1 floor.gooo > floor.html
```

This creates `floor.html`. Open it in a browser to read the highlighted source
in a self-contained page. No Gooo compiler is needed; this command highlights
the sample without executing it.

The published helper bundles the Gooo lexer with released **Chroma v2.27.0**.
Gooo highlighting was [accepted into Chroma v3 development](https://github.com/alecthomas/chroma/pull/1410);
that merge is separate from a Chroma release. See the
[consumer guide](examples/highlight-gooo/README.md) for installation, JSON output
and the exact availability distinction.

To explore language behavior next, run [your first native observation](docs/first-observation.md)
without a Gooo compiler, or choose a browser/native example from the
[experiment catalog](docs/experiments.md). [CONTRIBUTING.md](CONTRIBUTING.md)
explains how to add a native observation or a Gooo semantic bridge.

## First bridge: Python integer floor division

`bridges/python-floor/main.gooo` expresses Python-style floor division using
Gooo Integer division and explicit sign corrections. For example, `-7 / 3`
truncates to `-2` in the underlying integer calculation; this bridge returns `-3`.
The 120 comparisons cover dividends -7..7 and nonzero divisors -4..4.
This is a bounded semantic adapter, not a Python compiler or a general equivalence proof.
The upstream documentation revision and licensing context are in `provenance.json`.
For a practical migration example, read [Python integer division to Go](docs/python-go-integer-division.md):
it compares the native runtimes with the actual Gooo results and explains the negative-input counterexamples.
A [pinned GoLua witness](examples/lua-division-reference/README.md) also matches these
120 small pairs; its separate int64-wrap and zero-divisor observations show why
this does not establish general Lua/Python integer equivalence.
The executing Python runtime is recorded separately: it is not claimed to be that upstream revision.

## String-length units across languages

`bridges/text-length/main.gooo` gives UTF-8 bytes, Unicode code points and UTF-16
code units separate stable field identities. For `🙂` these are **4, 1, 2**;
for `가` they are **3, 1, 1**. Native Go, Python and Node.js operations
independently check all three fields on 27 inputs, including encoding boundaries
and 1024-byte strings. A 1025-byte input must be rejected.

Read [String length across Go, Python and JavaScript](docs/string-length-units.md) for the
executable example, counterexamples and scope. These are encoding units;
graphemes, display width, normalization and browser engines are excluded.

## Execution and completion have different input intent

An unfinished `-ab` group needs an error during execution and preservation during
completion. [The completion intent guide](docs/completion-input-intent.md) connects
[urfave/cli #2485](https://github.com/urfave/cli/pull/2485) with a Gooo activity that
gives the request mode and token classification stable identities. The verifier
reproduces nine original mismatches, 20 patched/race matches and 20 Gooo matches
across 12 distinct policy inputs. Gooo resolves the declared intent policy;
tokenization and arbitrary CLI grammar validation stay outside its scope.

```sh
python3 tools/verify_cli_completion.py --gooo .bin/gooo
```

## Defaults depend on presence

An explicit `0` or `false` should replace a default, not select it. The
[Tengo input-defaults bridge](docs/input-defaults.md) gives presence and value
separate stable field identities. It compares 48 unique native maps with Gooo,
including resets when an override disappears on a reused compiled script.
The native observer and Gooo bindings also reject out-of-domain inputs; these
adapter bounds do not restrict Tengo's general map semantics.

HCL adds a different distinction: an explicit null can acquire an optional
non-null default, while a required missing attribute fails conversion. The
[HCL null/default bridge](docs/hcl-null-defaults.md) compares twenty requests
with released HCL v2.24.0 and Gooo, retaining native nulls and the expected
required-missing diagnostic.

## Reproduce the semantic comparisons

Requires Python 3.9+, Go 1.27.3 and Node.js 22.23.1; no model, API key, service or paid runner.

```sh
mkdir -p .bin
GOBIN="$PWD/.bin" GOTOOLCHAIN=go1.27.3 go install github.com/kimjooyoon/meta-ontology-go/cmd/gooo@v0.6.38-dev
python3 tools/verify.py --gooo .bin/gooo
python3 tools/compare_text_length.py --gooo .bin/gooo
```

Inspect `evidence/summary.json`, `execution.json`, `cases.json`, and stderr.
Exit zero requires Gooo PASS and exactly all 120 expected comparisons.
A missing, partial, stale-version or malformed result fails closed.
CI retains evidence even on failure. The [offline evidence auditor](docs/audit-ci-evidence.md)
checks a downloaded bundle against its captured hashes, exact local source and
expected execution tuple without rerunning the engines. It also runs in required CI.
For a **Python-and-Git-only** replay, follow the
[published 17-summary snapshot recipe](docs/audit-ci-evidence.md#replay-the-published-17-summary-snapshot).
It uses retained evidence and a fixed source/execution tuple.
Artifact hashes bind files, not authorship;
GitHub's run and commit metadata provide the execution context.

## Project management

Before starting a candidate, use the [read-only contribution check](docs/contribution-candidate-check.md)
to collect recent merge witnesses, linked open/closed PRs and recent comments in
one bounded GitHub query. Gooo assigns a next-review reason; it never approves
submission or declares the work unclaimed. Offline CI checks all 32 policy inputs.

The [response planner](docs/contribution-response-planning.md) and
[repository profiles](docs/contribution-profile-planning.md) retain actor roles,
scope and material limitations before preparing a response. The
[real producer consumer](docs/producer-response.md) connects saved technical
observations to that plan while retaining unknown provenance and original failures.

For repeated local follow-up, the [saved-material comparison](docs/saved-followup.md)
retains a completed inspection only when all captured material, evaluation inputs
and scope match. New feedback, changed criteria or incomplete evidence require
inspection. This manual helper does not collect fresh remote activity or approve
a contribution.

Use Issues for bounded bridge proposals and counterexamples, and PRs for source.
See [CONTRIBUTING.md](CONTRIBUTING.md) and [ROADMAP.md](ROADMAP.md).
This project complements the [Gooo engine](https://github.com/kimjooyoon/meta-ontology-go)
and existing ecosystem projects. Upstream acceptance is decided by each upstream
project; a local passing bridge is never counted as an accepted contribution.

## Reusable native experiment reports

The [recorded Go test comparison](examples/go-test-comparison/README.md) reads
two saved `go test -json` captures with an explicit case list. It separates
new failures, resolved failures and controls even when both commands failed,
without rebuilding a project or installing Gooo. Missing or incomplete records
remain invalid; a difference alone is not a correctness verdict.

The [saved review reply check](docs/review-readback.md) compares an already
submitted GitHub review with captured replies. Missing comment-line evidence
leads to existing comment GETs, while original bodies and anchors remain bound.
It neither fetches nor publishes, and never recommends another POST.

The [32 bit Go integer parsing guide](docs/go-integer-width.md) answers a real
Cast maintainer request with an executed Linux/386 comparison. It explains the
parser-width trap, shows all nine boundary results, and links the complete
original failure/success capture. Read the saved results before repeating a run.

The [JavaScript differential driver](examples/js-differential/README.md) compares
a trusted snapshot script in Node.js and an exact Goja or Sobek commit, optionally against
a base commit. It retains typed case comparisons, source/runtime identities,
original outputs and hashes. Unmerged PR heads use a verified Git checkout rather
than relying on an unavailable canonical module version. The included example
reproduces a historical normalization difference at two pinned pre-fix revisions;
the guide links the accepted repair. A difference is not an approval or a
standards verdict. No Gooo compiler is required for this native helper.

## Upstream work

Contribution entry points observed October 22, 2026, with later acceptance
updates dated separately:

| Need | Contribution | Reproduction and scope |
| --- | --- | --- |
| Reuse text decoding with a custom configuration decoder | [Koanf #464](https://github.com/knadh/koanf/pull/464), submitted API change | [Public-API tests at the submitted commit](https://github.com/kimjooyoon/koanf/blob/8d167f6687338edfc10609cbd27e0effcf4901ba/tests/text_hook_test.go) cover custom text representations, duration composition, errors and unknown-key rejection. Native tests passed within the documented exclusions; hosted CI and acceptance remain unproven. |
| Understand byte counts versus UTF-8 regexps | [GoAWK Unicode guide](https://github.com/benhoyt/goawk/blob/592620f9bdce8a2fb9abb3ba5d4cfc1014e20375/docs/unicode.md), [#308 merged October 25, 2026](https://github.com/benhoyt/goawk/pull/308) | [Choose consistent string units](docs/string-length-units.md#keep-goawk-positions-in-one-mode). This documentation change does not alter the interpreter. [Pinned CLI observations](https://gist.github.com/kimjooyoon/6d6855f852800045a22e3db0a3d94ff5/871a8d5f75acf3ef6dc64251264c5a814e9fa4fb) reproduce the two byte/character-mode examples and preserve the missing-`gawk` full-suite failure. |
| Review ownership or nested-map fixes | [GoJq constant ownership review](https://github.com/itchyny/gojq/pull/320#pullrequestreview-5610173011) and [Koanf nil-map review](https://github.com/knadh/koanf/pull/461#pullrequestreview-5610513013) | The [native experiment index](docs/experiments.md#native-observations-no-gooo-compiler-needed) links frozen observations, tested source identities, remaining differences and test limitations. Reviews are independent evidence, not acceptance. |

These entry points require no Gooo compiler. Read the dated scope before adapting
an experiment; the upstream PR is authoritative for its current status.

[Yaegi #1738](https://github.com/traefik/yaegi/pull/1738) fixes an existing
interpreter report: operator assignments to compiled interface slices can lose
the stored value and return a nil pointer. The patch introduces no Gooo dependency.

```sh
python3 tools/verify_yaegi.py
```

This fetches the pinned original and patch revisions, injects the same regression
tests, and requires eleven original failures followed by sixteen patched passes and
sixteen race-checked passes. Original JSON test events are retained in
`evidence/yaegi-1736/`. The separately recorded mixed-type blank-assignment counterexample still fails
on both revisions. This focused regression does not certify Yaegi's full suite.
See the [contribution ledger](docs/contributions.md) for scope and acceptance status.

[Chroma #1410](https://github.com/alecthomas/chroma/pull/1410) merged Gooo source
highlighting on October 22, 2026, with no Gooo runtime dependency. The accepted
change targets Chroma v3 development; the published consumer below loads the
same XML into the released Chroma v2.27.0 runtime.
Try the [published-Chroma consumer](examples/highlight-gooo/README.md) now: it renders
self-contained HTML or source-preserving JSON tokens without building a Chroma fork.

```sh
python3 tools/verify_chroma.py
```

The command fetches the exact submitted revision, runs the full Chroma tests,
race-checks the Gooo fixtures, verifies generated metadata and checks that all
128 expected tokens reconstruct the two source fixtures without Error tokens.
Logs and hashes are retained under `evidence/chroma-gooo/`. Upstream acceptance
is separately established by the merged PR and its [successful test, lint and
generation checks](https://github.com/alecthomas/chroma/actions/runs/39665018209).
The [dated acceptance record](docs/observations/2026-10-25-chroma-accepted.json)
binds the submitted heads, upstream merges and checks.

[Chroma #1411](https://github.com/alecthomas/chroma/pull/1411), also merged on
October 22, 2026, corrects Go
imaginary literals such as `0b10i` and `0x1p-2i` being split before their `i`.
Native Go compilation and scanner output independently establish the eighteen-case
fixture's input scope; eleven token streams change and seven controls stay equal.

```sh
python3 tools/verify_chroma_go_numbers.py
```

This retains the original failing regression, patched/race passes, full tests and
native token observations under `evidence/chroma-go-numbers/`. Its upstream
[test, lint and generation checks passed](https://github.com/alecthomas/chroma/actions/runs/39677077130).
The Go lexer patch and the Gooo language lexer are separate accepted contributions.

## Text editing: one Delete press, one edit

[Bubbles #1072](https://github.com/charmbracelet/bubbles/pull/1072) fixes Delete
removing the next newline while deleting a line's final character. The
[independent editing bridge](docs/delete-forward-newline.md) expresses the edit
in Gooo and compares eight observations from the actual original/patched textarea.

```sh
python3 tools/verify_bubbles_delete.py --gooo .bin/gooo
```

Three original mismatches become eight patched, race-checked and Gooo matches.
The packet retains original test events and exact source hashes. Native cursor
positions are rune indices; the Gooo input explicitly names its UTF-8 byte offset.
This focused comparison is separate from upstream CI approval and acceptance.

## Proposed criterion study: wrapped TCP read resets

The [Traefik criterion packet](proposals/traefik-read-reset/README.md) preserves
original source, a two-file proposed diff and a real loopback TCP reset reproducer.
It compares sixteen native decisions with a bounded Gooo policy, including
`NO_LOG` for nil errors and controls that keep write failures in ERROR.

```sh
python3 tools/verify_read_reset.py --gooo .bin/gooo
```

This is an owned, unsubmitted proposal. Its standalone checks do not replace
Traefik's full validation or human-authored upstream conversation requirements.
