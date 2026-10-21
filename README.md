# Gooo Language Bridge

Small, reproducible bridges between OSS language behavior and Gooo source.
Gooo owns the semantic activity and stable identity; an independent language
runtime supplies finite expected observations. Every run keeps source hashes,
compiler identity, runtime identity, exit codes and the original Gooo receipt.

## First bridge: Python integer floor division

`bridges/python-floor/main.gooo` expresses Python-style floor division using
Gooo Integer division and explicit sign corrections. For example, `-7 / 3`
truncates to `-2` in the underlying integer calculation; this bridge returns `-3`.
The 120 comparisons cover dividends -7..7 and nonzero divisors -4..4.
This is a bounded semantic adapter, not a Python compiler or a general equivalence proof.
The upstream documentation revision and licensing context are in `provenance.json`.
The executing Python runtime is recorded separately: it is not claimed to be that upstream revision.

## Reproduce

Requires Python 3.9+ and Go 1.27.3; no model, API key, service or paid runner.

```sh
mkdir -p .bin
GOBIN="$PWD/.bin" GOTOOLCHAIN=go1.27.3 go install github.com/kimjooyoon/meta-ontology-go/cmd/gooo@v0.6.38-dev
python3 tools/verify.py --gooo .bin/gooo
```

Inspect `evidence/summary.json`, `execution.json`, `cases.json`, and stderr.
Exit zero requires Gooo PASS and exactly all 120 expected comparisons.
A missing, partial, stale-version or malformed result fails closed.
CI retains evidence even on failure. Artifact hashes bind files, not authorship;
GitHub's run and commit metadata provide the execution context.

## Project management

Use Issues for bounded bridge proposals and counterexamples, and PRs for source.
See [CONTRIBUTING.md](CONTRIBUTING.md) and [ROADMAP.md](ROADMAP.md).
This project complements the [Gooo engine](https://github.com/kimjooyoon/meta-ontology-go)
and existing ecosystem projects. Upstream acceptance is decided by each upstream
project; a local passing bridge is never counted as an accepted contribution.

## Upstream work

[Yaegi #1738](https://github.com/traefik/yaegi/pull/1738) fixes an existing
interpreter report: operator assignments to compiled interface slices can lose
the stored value and return a nil pointer. The draft introduces no Gooo dependency.

```sh
python3 tools/verify_yaegi.py
```

This fetches the pinned original and patch revisions, injects the same regression
tests, and requires eight original failures followed by thirteen patched passes and
thirteen race-checked passes. Original JSON test events are retained in
`evidence/yaegi-1736/`. This focused regression does not certify Yaegi's full suite.
See the [contribution ledger](docs/contributions.md) for scope and acceptance status.
