# Verify a downloaded CI evidence bundle offline

`tools/audit_evidence.py` checks the captured files against their recorded hashes,
checks source references against an exact local Git commit, and requires the
expected execution revision and GitHub run ID. It makes no network request,
executes no captured script, and does not need a Gooo compiler, Node.js or Go.
Python 3.9+ and Git are sufficient.

This is a file-integrity check. It does not independently authenticate GitHub's
run metadata, prove who authored the source, re-execute a runtime, or decide
whether a language behavior is correct. Use the native verifiers and original
Gooo receipts for those semantic questions.

## Obtain the expected identities first

Before downloading, inspect the canonical repository's PR, required check and
workflow run. Record the exact PR source head, tested merge revision and run ID.
Check that the tested merge has the expected base/head parents and that the run
belongs to that PR head. Obtain the artifact from that run, and compare the ZIP's
SHA-256 and size with GitHub's artifact metadata before extracting it. These
identity and transport checks are outside this offline tool.

Use a trusted copy of the auditor. Have the source head available as a local Git
commit; a full 40-character lowercase SHA is required. All referenced source objects must already be available locally. Lazy fetching
is disabled with [Git's `GIT_NO_LAZY_FETCH` guard](https://git-scm.com/docs/git)
for the Git reads. Source files are read from
Git objects, so uncommitted working-tree changes do not silently change the
reference. The execution revision is usually the temporary PR merge revision,
which can differ from the source head even when their file trees are identical.

For example, [PR #25](https://github.com/kimjooyoon/gooo-language-bridge/pull/25)
produced the following checked tuple in [run 39715468593](https://github.com/kimjooyoon/gooo-language-bridge/actions/runs/39715468593):

```sh
python3 tools/audit_evidence.py \
  --artifact /absolute/path/to/extracted-evidence \
  --source-revision 5dbdca6aa96ed2a265274ef554b0007fccb7b4b8 \
  --execution-revision 7cb7f602830bfa2ed1d8b04a5edb1222f534b103 \
  --run-id 39715468593
```

That bundle has 13 summaries, two nested JavaScript reports and 576 hash
references, including repeated references. It binds 407 distinct captured files
and 56 distinct source files. Those counts describe this example, not a general
minimum for all future bundles. Artifacts expire after seven days; use a newly
verified run's identities for a new download. Do not substitute the current
branch head or today's run ID into an old artifact.

## Read the result

A successful invocation exits zero and emits `PASS_INTEGRITY`, the supplied
source/execution/run tuple, reference and file counts, and SHA-256 fingerprints
for every summary and nested native report. A missing file, changed output,
wrong source hash, wrong execution tuple, malformed/duplicate JSON key, extra
unhashed captured file, failed summary or incomplete inventory exits nonzero.
Failure emits `FAIL_CLOSED` on stderr and no success report on stdout.

The inventory names this workbench's summary schemas and two native reports.
It selects 14 summaries when the trusted source commit contains
`bridges/input-defaults/gooo.workspace.json`, or the original 13 otherwise.
Selection reads the local Git tree, never the untrusted artifact inventory; a
current source cannot silently accept a bundle missing the new verifier.
Native report decisions `MATCH` and `DIFFERENCES` are both legitimate
observations; a known difference can be the expected result of a passing wrapper
check. This auditor does not turn a difference into equivalence or acceptance.
Adding or removing a verifier requires an explicit inventory update.

Two older summaries (`chroma-gooo` and `yaegi-1736`) do not record a run tuple.
Their filenames are the only missing-context exceptions. Their captured files
are still hashed, but the auditor cannot bind those two summaries directly to
an execution revision. It reports this limitation explicitly. If either summary
supplies any execution-context field, a complete matching tuple is required.

All captured files must be covered by a hash reference except the manifests
and `integrity-audit.json` itself. The latter is this check's output and is
ignored when auditing a downloaded bundle: an existing success report is never
a substitute for running the auditor. Manifest fingerprints make changes
inspectable, but cannot authenticate a fully replaced packet. Hashes are not
signatures; the previously verified GitHub run and artifact digest provide the
external binding.

## CI and bounds

The existing single, 12-minute CI job runs this audit after the native/Gooo
verifiers and before uploading evidence. Inside that job, the checked-out merge
revision supplies both the source reference and expected execution revision.
The audit does not add a runner, matrix, service, API token or model call.

Audit a quiescent extracted directory. Symlinks and nonregular entries are
rejected; manifest paths cannot escape through absolute paths, `..`, aliases or
Windows separators. The current limit is 2,048 files, 4,096 total entries and
256 MiB of captured file data. These bounds do not make extraction safe or
protect against a concurrent filesystem writer. Extract archives safely before
calling the auditor. The tool never extracts an archive itself.

Focused regression tests cover changed outputs, omitted manifests/captures,
wrong run/source identities, dirty working trees, duplicate JSON, unsafe paths,
symlinks and unhashed additions. They use a temporary local Git repository and
make no network request.
