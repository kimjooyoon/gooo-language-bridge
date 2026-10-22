# Gooo Language Bridge

Small, reproducible bridges between OSS language behavior and Gooo source.
Gooo owns the semantic activity and stable identity; an independent language
runtime supplies finite expected observations. Semantic bridge runs keep source hashes,
compiler identity, runtime identity, exit codes and the original Gooo receipt.

New here? Run [your first native observation](docs/first-observation.md): three
small Goja/Node.js cases, with no Gooo compiler required. Then
[choose a contribution path](CONTRIBUTING.md) for a native observation or a Gooo
semantic bridge.

## Try source highlighting

With Go 1.25+, download the release's [floor.gooo sample](https://github.com/kimjooyoon/gooo-language-bridge/releases/download/examples/highlight-gooo/v0.1.1/floor.gooo)
and render it without cloning this repository or installing a Gooo compiler:

```sh
go run github.com/kimjooyoon/gooo-language-bridge/examples/highlight-gooo@v0.1.1 floor.gooo > floor.html
```

Open the self-contained HTML file in a browser, or use `-format json` for tokens.
The [consumer guide](examples/highlight-gooo/README.md) explains installation,
stdin, source preservation and scope. Highlighting is separate from executing
the semantic comparisons below.

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
Artifact hashes bind files, not authorship;
GitHub's run and commit metadata provide the execution context.

## Project management

Before starting a candidate, use the [read-only contribution check](docs/contribution-candidate-check.md)
to collect recent merge witnesses, linked open/closed PRs and recent comments in
one bounded GitHub query. Gooo assigns a next-review reason; it never approves
submission or declares the work unclaimed. Offline CI checks all 32 policy inputs.

Use Issues for bounded bridge proposals and counterexamples, and PRs for source.
See [CONTRIBUTING.md](CONTRIBUTING.md) and [ROADMAP.md](ROADMAP.md).
This project complements the [Gooo engine](https://github.com/kimjooyoon/meta-ontology-go)
and existing ecosystem projects. Upstream acceptance is decided by each upstream
project; a local passing bridge is never counted as an accepted contribution.

## Reusable native experiment reports

The [JavaScript differential driver](examples/js-differential/README.md) compares
a trusted snapshot script in Node.js and an exact Goja or Sobek commit, optionally against
a base commit. It retains typed case comparisons, source/runtime identities,
original outputs and hashes. Unmerged PR heads use a verified Git checkout rather
than relying on an unavailable canonical module version. The included example
reproduces a known normalization difference; a difference is not an approval or
a standards verdict. No Gooo compiler is required for this native helper.

## Upstream work

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

[Chroma #1410](https://github.com/alecthomas/chroma/pull/1410) adds Gooo source
highlighting through a standalone XML lexer, with no Gooo runtime dependency.
Try the [published-Chroma consumer](examples/highlight-gooo/README.md) now: it renders
self-contained HTML or source-preserving JSON tokens without building a Chroma fork.

```sh
python3 tools/verify_chroma.py
```

The command fetches the exact submitted revision, runs the full Chroma tests,
race-checks the Gooo fixtures, verifies generated metadata and checks that all
128 expected tokens reconstruct the two source fixtures without Error tokens.
Logs and hashes are retained under `evidence/chroma-gooo/`. Upstream CI approval
and acceptance remain separate from this independent proof.

[Chroma #1411](https://github.com/alecthomas/chroma/pull/1411) also corrects Go
imaginary literals such as `0b10i` and `0x1p-2i` being split before their `i`.
Native Go compilation and scanner output independently establish the eighteen-case
fixture's input scope; eleven token streams change and seven controls stay equal.

```sh
python3 tools/verify_chroma_go_numbers.py
```

This retains the original failing regression, patched/race passes, full tests and
native token observations under `evidence/chroma-go-numbers/`. The submitted Go
lexer patch and the Gooo language lexer are separate contributions.

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
