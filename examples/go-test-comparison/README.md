# Compare recorded Go tests without rebuilding

Two test commands can both fail while a patch fixes one case and breaks another.
This Python-only helper compares their recorded test outcomes and retains the
original inputs. It makes no network request and executes no Go code or Gooo.

## Try the included fixture

From the repository root, with Python 3.9+:

```sh
python3 tools/compare_go_tests.py \
  --cases examples/go-test-comparison/cases.json \
  --base examples/go-test-comparison/base.jsonl \
  --head examples/go-test-comparison/head.jsonl \
  --out evidence/my-go-test-comparison
```

Choose a new output directory on every run. **The included records are synthetic
protocol fixtures, not captured Go executions.** This example exits **1**, with
a complete comparison and these four results:

| Case ID | Base | Head | Report group |
| --- | --- | --- | --- |
| `new-failure` | pass | fail | `introduced_failures` |
| `resolved` | fail | pass | `resolved_failures` |
| `still-failing` | fail | fail | `failed_both` |
| `control` | pass | pass | `passed_both` |

`report.json` copies no success or approval claim from the command's exit code.
Exit **0** means the recorded head packages completed without failures;
exit **1** means the comparison is complete but a head package failed;
exit **2** means the capture or comparison is invalid. Read `decision`, the case
groups and package context together. A completed comparison is not a passing
test suite or an approved patch.

## Supply your own captures

Run the same named contract tests at the revisions you intend to compare and
retain the unmodified output from `go test -json -count=1`. Also retain the
source revisions, fixture, actual command, runtime, stderr and process exit
codes separately. This helper cannot recover that provenance from a JSON log.
The [Go test2json documentation](https://pkg.go.dev/cmd/test2json) describes the
test/package events produced by `go test -json`.

List the exact leaf tests you intend to compare in a JSON array:

```json
[
  {"id": "custom-set", "package": "example.test/project", "test": "TestCustomSet/slice"}
]
```

Each ID and package/test pair must be unique. A test with observed subtests is
a parent and cannot stand in for those cases. Selected tests must have explicit
run and pass/fail events in complete package captures. A missing case, selected
skip, unfinished run, repeated invocation, duplicate JSON key, build failure
or unsupported event makes the comparison invalid. Regular test events and
parallel pause/continue events are supported; benchmarks are excluded. Each
input is limited to 8 MiB and the domain to 1,000 selected cases.

The result also retains unselected leaf failures, parent failures and package
outcomes. Parent failures are not counted as additional selected cases, and
can contain failures beyond a child test. The selected domain does not prove
that every test in the source was run.

`failed_both` compares statuses only: the failure cause can change. In the
[KubeStellar review packet](https://gist.github.com/kimjooyoon/35580df5fea06592b962f205eef41434/731b886c85e6eaebe91004fde9af5bee3bf3be4e#file-readme-md),
three tests change from a recovered panic to incorrect grouping while still
failing. Read the original outputs before interpreting a transition as a
regression, correction or unchanged defect. Likewise, a passing test does not
establish that its assertions express the right contract.

The fresh output directory retains the exact case/log bytes and the two Python
source files, plus their SHA-256 digests. Invalid comparisons retain an error
and inputs captured before the failure. Hashes bind saved bytes; they do not
authenticate the source revision, runtime, author, or execution. The report
keeps those limits explicit and never approves an upstream contribution.

This is a native companion to the Gooo bridge workflow, reusing the existing
typed comparison classifier. It does not add a Gooo dependency to Go projects.

## Replay a real retained review

The [urfave/cli review packet](https://gist.github.com/kimjooyoon/358a7a66e67514e76dcc2c27a12e522b/05dad5f80b7a0b205c6241042b6b423a1aa9182a#file-readme-md)
contains the original eight-case test output and fixture. To analyze those saved
records without rebuilding the Go project, download the two text files explicitly:

```sh
mkdir -p evidence
records=$(mktemp -d evidence/urfave-records.XXXXXX)
curl --fail --location --output "$records/base.jsonl" \
  https://gist.githubusercontent.com/kimjooyoon/358a7a66e67514e76dcc2c27a12e522b/raw/05dad5f80b7a0b205c6241042b6b423a1aa9182a/base-go-test.jsonl
curl --fail --location --output "$records/head.jsonl" \
  https://gist.githubusercontent.com/kimjooyoon/358a7a66e67514e76dcc2c27a12e522b/raw/05dad5f80b7a0b205c6241042b6b423a1aa9182a/head-go-test.jsonl
python3 tools/compare_go_tests.py \
  --cases examples/go-test-comparison/urfave2510-cases.json \
  --base "$records/base.jsonl" \
  --head "$records/head.jsonl" \
  --out "$records/comparison"
```

Expected: exit **1**, four introduced failures, one resolved failure and three
passing controls. This re-analyzes saved records; it does not run those tests,
verify the claimed Go revision/runtime, or establish their current upstream
status. The packet explains the original execution and scope separately.
