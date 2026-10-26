# Stop CI downloads at the HTTP error

[minikube #23944](https://github.com/kubernetes/minikube/issues/23944) requests
that failed HTTP downloads stop scripts before they extract or execute an error
page. Adding `curl --fail` alone is insufficient when a command substitution,
pipeline, or multi-command Make recipe hides its exit status.

This package preserves a local comparison of
[base `34f70057`](https://github.com/kubernetes/minikube/commit/34f70057d29a36eae8b8bec815b33ba1599ff80f)
and [candidate `93654435`](https://github.com/kimjooyoon/minikube/commit/93654435929c6df7c70d8e8003af659346faa3c9):

| Observation | Base | Candidate |
| --- | --- | --- |
| 18 HTTP-error cases | Fail | Pass |
| 13 normal-response and status-retry controls | Pass | Pass |
| Total matching the checked behavior | 13/31 | 31/31 |

The 31.667-second run used real curl, Bash and Make on macOS. A loopback server
returned HTTP 200, 404 and 500. Tests cover a direct download, nested Kubernetes
version lookup, installer pipelines, the linter checksum recipe, GitHub CLI
version/archive downloads, and both status-post retry functions. Existing status
retry exhaustion remains successful; this change does not redefine that policy.
The nine successful download paths preserve their silent/progress modes, and
silent curl calls retain visible errors.

## Inspect the evidence

- [Raw comparison report](captured/report.json) and
  [runtime/progress summary](captured/http-validation-summary.json).
- [Source binding](source-binding.json): all 26 changed file hashes and Git blobs,
  plus the nine before/after files used by the HTTP harness. Captured source bytes
  match the respective commits, and all 62 executed fragment hashes match.
- [Shell syntax results](captured/shell-syntax.json) and
  [workflow shell-block syntax results](captured/workflow-syntax-final.json).
  Syntax success does not establish runtime success for the unexecuted paths.
- [`captured/sources/`](captured/sources/) retains complete source files with
  their original copyright notices. Each `captured/before-*` or `after-*`
  directory contains the executed fragment, stdout/stderr and applicable curl,
  stub and retry logs. For example,
  [failed base lookup](captured/before-lookup-lookup-404/) and
  [stopped candidate lookup](captured/after-lookup-lookup-404/).
- [`file-integrity.json`](file-integrity.json) hashes the packaged files.

Original reports and logs are copied byte-for-byte, including their local paths
and loopback port. `fixture-token` in status-call logs is generated test data.
No account credential was read or used. Duplicate generated tool adapters and
test binaries are omitted; the unchanged harness recreates them on a new run.

## Reproduce

Requirements: Python 3.9+, Git, GNU Make, Bash and curl at the paths used by the
harness (`/usr/bin/make`, `/bin/bash`, `/usr/bin/curl`). Use a clean minikube
checkout at the candidate commit with the base commit and required file objects
already available. The wrapper verifies all 26 modified files before execution
and disables Git's automatic object fetch. It installs or downloads nothing.

From the root of this workbench:

```sh
python3 reviews/minikube-23944/run.py \
  --source /path/to/minikube \
  --output /tmp/minikube-http-check
```

The output directory must be new or empty. Read its
`latest-http-validation.json` pointer for the new run's report. The wrapper loads
the exact [executed harness](verify_http_failures.py), changing only its source
and output directories. A new run produces new paths, port and timing; the
expected behavioral result is 18 failing base cases, 13 base controls, and all
31 candidate cases passing.

## Scope and limits

These are partly extracted source fragments with inert installation stubs.
They do not run Kubernetes, installers, real GitHub POSTs, or hosted CI. Curl
URLs are redirected to loopback; transport deadlines and curl-config isolation
are harness safeguards. The linter fixture uses a small generated archive;
the GitHub CLI fixture records extraction/move calls without installing it.
Workflow fragments use the documented
[GitHub Actions shell settings](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell),
not an actual Actions runner. No full-suite success, maintainer acceptance, or
CLA status is established by these records.

The executed harness and new wrapper are covered by this repository's MIT
license. Captured minikube source and source-derived snippets remain under
minikube's [Apache License 2.0](LICENSE.upstream); their original copyright
notices are preserved in the complete captured sources.
