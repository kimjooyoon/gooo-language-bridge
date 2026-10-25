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

## Replay the published 17-summary snapshot

The [25 October 2026 evidence snapshot](https://github.com/kimjooyoon/gooo-language-bridge/releases/tag/evidence/contribution-planning-2026-10-25)
retains the original ZIP from [PR #37](https://github.com/kimjooyoon/gooo-language-bridge/pull/37),
[run 40145354927](https://github.com/kimjooyoon/gooo-language-bridge/actions/runs/40145354927),
beyond the seven-day CI artifact lifetime. Download its
[bridge-evidence-40145354927.zip](https://github.com/kimjooyoon/gooo-language-bridge/releases/download/evidence/contribution-planning-2026-10-25/bridge-evidence-40145354927.zip)
and [provenance.json](https://github.com/kimjooyoon/gooo-language-bridge/releases/download/evidence/contribution-planning-2026-10-25/provenance.json).
The ZIP is **746502 bytes**, SHA-256
`44ecda75c8b6a1e3ae44631d6b0a05322a3864c0853d80b42381f0bdd91f645e`.
Check these transport identities against the release provenance and original
GitHub artifact metadata before extracting the ZIP into a fresh directory.

Obtain the matching source in a separate checkout:

```sh
git clone --depth 1 --branch evidence/contribution-planning-2026-10-25 \
  https://github.com/kimjooyoon/gooo-language-bridge.git bridge-audit
cd bridge-audit
git checkout --detach 95d437d24554edbddb59b1754f0ce11978b84494
```

Run the auditor from that checkout, replacing the artifact path with your
extracted directory:

```sh
python3 tools/audit_evidence.py \
  --artifact /absolute/path/to/extracted-evidence \
  --source-revision 95d437d24554edbddb59b1754f0ce11978b84494 \
  --execution-revision 2c44b42dfd96fb443c969c4b962ae64c017804c6 \
  --run-id 40145354927
```

This requires Python and Git, without installing or executing Gooo, Go or
Node.js. Expected output is `PASS_INTEGRITY`, inventory
`contribution-profiles-17`, **17 summaries**, **two native reports**, **842 hash
references**, **605 captured files** and **115 source files**. These counts
describe this snapshot, not a requirement to copy into later runs.

The release tag pins accepted main. Its tree matches the tested merge, whose
parents are base `1bf12d6de9b9fcb2925b9d009d8d77f513e2f5ce` and PR head
`7beb0fa6e078ad961f2c136008a1b283ba9d8168`. The accepted source, PR head and
execution revision are distinct identities; use the tuple above unchanged.
The snapshot includes synthetic B1/B2 planning packets and existing bounded
native observations. It is not a real ports P1 integration or upstream
acceptance record. Release provenance and hashes retain their separate role
from independently authenticating the execution or judging its semantics.

## Historical 13-summary example

The shallow checkout above contains the 17-summary snapshot only. Make this
older source commit available locally before using the following historical tuple.

[PR #25](https://github.com/kimjooyoon/gooo-language-bridge/pull/25)
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
The trusted source tree selects the inventory using cumulative markers:

| Source workspace markers | Inventory | Summaries |
| --- | --- | ---: |
| None of the following | `base-13` | 13 |
| `bridges/input-defaults/gooo.workspace.json` | `input-defaults-14` | 14 |
| Above plus `bridges/hcl-null-defaults/gooo.workspace.json` | `hcl-null-defaults-15` | 15 |
| Above plus `bridges/contribution-response/gooo.workspace.json` | `response-planning-16` | 16 |
| Above plus `bridges/contribution-profiles/gooo.workspace.json` | `contribution-profiles-17` | 17 |
| Above plus `bridges/producer-response/contract.json` | `producer-response-18` | 18 |

An inconsistent marker chain is rejected. A newer source cannot omit its
required evidence by claiming an older inventory in the artifact.
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
