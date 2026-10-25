# Compare saved follow-up material

Repeatedly reading the same saved PR material spends time without resolving a
maintainer's next request. `tools/check_saved_followup.py` compares two explicit
local bundles and reports whether a completed inspection of the same captured
material and evaluation can be retained.

```sh
python3 tools/check_saved_followup.py \
  --current current-bundle --previous previous-bundle \
  --output followup-comparison.json
```

The command performs no collection, inspection, execution, posting or baseline
update. It uses Python 3.9+ and its standard library on POSIX systems with
descriptor-relative, no-follow file operations (macOS/Linux). Omit `--output` to
write the report to stdout. An explicit output must be outside both evidence
bundles and must not already exist; existing files and links are never overwritten.

| Report | Meaning | Next action |
| --- | --- | --- |
| `RETAIN_UNCHANGED` | Complete saved inputs and evaluation match a usable completed inspection. | Retain that local inspection for this exact material. |
| `INSPECT` | A component changed, coverage is incomplete, or the prior inspection is missing or unusable. | Inspect the changed or missing material. |
| `INSPECT` with `INVALID_CURRENT_BUNDLE` | Current input fails the bundle contract. The command exits 2. | Repair the bundle before relying on the comparison. |

A valid report exits zero for either decision. Exit zero is not an approval to
submit a contribution. `effect` is always `none`.

## Capture the complete comparison scope

Each bundle contains `snapshot.json` and the captured files named below. This is
a format example; replace its names and scope with the actual inspected material.
Mark a component `complete` only when the relevant scope was captured completely.
An observed empty comment or check collection needs an explicit file containing
that empty collection. Missing evidence must not be represented as observed empty.

```json
{
  "schema": "gooo/saved-followup-snapshot/v1",
  "subject": "owner/repository#123",
  "components": {
    "head": {"coverage": "complete", "files": ["head.json"]},
    "feedback": {"coverage": "complete", "files": ["feedback.json"]},
    "checks": {"coverage": "complete", "files": ["checks.json"]},
    "implementation": {"coverage": "complete", "files": ["inspector.py"]},
    "policy": {"coverage": "complete", "files": ["review-policy.txt"]},
    "schemas": {"coverage": "complete", "files": ["report-schema.json"]},
    "invocation": {
      "coverage": "complete",
      "argv": ["python3", "inspector.py", "--mode", "follow-up"],
      "selection": "All comments and reviews from every actor; exact head checks."
    },
    "scope": {"coverage": "complete", "files": ["selection-recipe.json"]}
  }
}
```

Include all implementation, configuration, schema and selection inputs that can
change the inspection. The evaluator digest binds `implementation`, `policy`,
`schemas`, `invocation` and `scope`. File components bind both relative names and
actual bytes. Subject, coverage, argument order, selection text and the original
manifest bytes also participate in the comparison. Even a manifest-only byte
change requires inspection. The report identifies changed components and retains
the exact prior receipt and result references when usable.

The existing contribution candidate collector does not capture PR head and check
records. Its output alone cannot provide a complete bundle. This tool does not
infer missing coverage, fetch additional pages, or filter feedback by actor role.
A new captured comment from any actor changes `feedback`.

Allowed coverage values are `complete`, `partial`, `unknown` and `missing`. A
non-complete component always prevents `RETAIN_UNCHANGED`. Every component is
required; malformed current declarations are refused. A file component declared
complete must name at least one file. Unknown fields and duplicate JSON keys in
`snapshot.json` and `inspection.json` are refused. Captured payload files remain
opaque bytes. Paths must be relative regular files inside the bundle, with no symlink
components or traversal. Limits are 64 captured files, 128 KiB per file and 1 MiB
per bundle, including the previous receipt and result.

## Bind a completed inspection

The previous bundle also needs `inspection.json` and its actual result file:

```json
{
  "schema": "gooo/saved-followup-inspection/v1",
  "status": "completed",
  "exit_code": 0,
  "snapshot_sha256": "sha256:<snapshot digest>",
  "evaluation_sha256": "sha256:<evaluation digest>",
  "result": {
    "path": "inspection-result.json",
    "sha256": "sha256:<digest of actual nonempty result bytes>"
  }
}
```

After the inspection has actually completed successfully, bind its snapshot and
evaluation using the report's `current_binding`. Bind the actual result bytes
with SHA-256. The result must be separate from the manifest, receipt and captured
input files. The tool deliberately has no command that manufactures a completion
receipt or promotes a comparison report to a completed inspection.

Running, failed, partial or unknown completion, a nonzero or non-integer exit
code, changed bindings, and missing, empty or tampered result files all require
inspection. A missing or malformed previous bundle also requires inspection; it
never silently establishes an unchanged result.

## Boundaries

These are unsigned local declarations. Matching hashes establish byte bindings;
they do not authenticate the inspection process, prove that the selected scope
was complete, or detect new remote activity after capture. The caller must decide
when to collect fresh material. Retention does not extend a freshness deadline.

This helper is separate from Gooo's contribution and response policies. It does
not infer semantic equivalence, maintainer usefulness, remote acceptance or
posting authority. It leaves existing B1/B2 decisions unchanged and does not fix
stale action pointers. Its own tests use synthetic bundles; those tests are not
external adoption or evidence of saved time in another maintainer's workflow.
