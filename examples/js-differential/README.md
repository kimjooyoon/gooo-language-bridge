# Compare JavaScript snapshots with pinned Goja or Sobek

For a small first run and a contribution path, start with
[your first native observation](../../docs/first-observation.md).

This driver turns a small JavaScript experiment into a retained native comparison
without editing an engine checkout or publishing another CI workflow. It was built
from real review work: an unmerged Goja PR head could not be fetched as a canonical
Go module version. The driver instead fetches and verifies its exact Git commit,
then builds an isolated observer with local module replacement. Inherited Git
working-tree/index/object-directory and injected Git configuration variables are
removed from child environments; caller environment values are left unchanged.

## One reproducible report

Requires Python 3.9+, Git, Go and Node.js. Go 1.27.3 is selected through GOTOOLCHAIN;
Go may download that toolchain and the pinned source's module dependencies.
No model, API key, account token or paid service is used.

From the repository root:

```sh
python3 tools/compare_js.py \
  --script examples/js-differential/normalize.js \
  --base a6ef56644a78f34dfcd246aa8acf03ad659f1c4e \
  --head 64adc8bb4d51821549c138900ca6bc31194f403d \
  --out evidence/my-normalize-report
```

Use a fresh output directory; existing directories are refused. Both commits
above predate the repair. This historical example reproduces the
[reported Goja normalization boundary](https://github.com/dop251/goja/issues/820):
24 cases, 12 head differences from Node, all also present in the base. It exits
**1**, intentionally. It does not fix the bug. Original Node/Goja snapshot bytes,
stdout/stderr for every step, source revision/tree, module files and license,
runtime identities, observer binary hashes and file digests remain in the report.
The observer template and the actual rendered Go source are both retained.

[Goja #825](https://github.com/dop251/goja/pull/825) merged on October 26, 2026,
preserving lone UTF-16 surrogates during normalization. Its
[accepted source and regression tests](https://github.com/dop251/goja/commit/6b6a90e519465e9b51198b64bff8aedc2cfd9b1e)
preserve `0xD800` in `"\ud800".normalize().charCodeAt(0)` instead of replacing
it with `0xFFFD`. Inspect UTF-16 units inside JavaScript before exporting a Go
string, which can lose this distinction. The command above intentionally keeps
its pre-fix pins and expected exit 1; its saved results do not describe the
merged revision or establish which published releases include the repair.

## Choose an engine

`--engine` selects a fixed repository/module pair; the default remains `goja`.
The fetched source's module declaration must match. Both providers use the same
observer code, with only the selected import changed before building.

| Engine | Repository | Go module |
| --- | --- | --- |
| `goja` | `dop251/goja` | `github.com/dop251/goja` |
| `sobek` | `grafana/sobek` | `github.com/grafana/sobek` |

This Sobek example observes an [existing author's JSON.parse fix, PR 165](https://github.com/grafana/sobek/pull/165)
by Huzaifa-Asif; this workbench does not claim authorship of that fix:

```sh
python3 tools/compare_js.py --engine sobek \
  --script examples/js-differential/json-reviver.js \
  --base 87a47258b7dcb6579c5cdfebbe07a9a1203cb719 \
  --head 6713561da465808c4f0bc73c7eb447a921a05092 \
  --head-ref refs/pull/165/head --out evidence/my-json-reviver-report
```

The 54 observations cover three JSON roots and 18 reviver forms: non-callable
values, objects that must not be coerced, revoked proxies, callable transforms,
deletion, exceptions, holder binding and traversal order. The base differs from
Node in the three `null` reviver cases; the patch matches all 54, with no introduced
differences in this corpus. Non-callable revivers are ignored by the
[JSON.parse algorithm](https://tc39.es/ecma262/multipage/structured-data.html#sec-json.parse).
Error names and observable calls are compared; engine-specific error messages
are outside this experiment. This example exits **0**. The SHA binds the source;
a changed PR ref fails closed. Omit `--head-ref` to fetch the exact SHA directly.

| Exit | Report decision | Meaning |
| ---: | --- | --- |
| 0 | MATCH | Head agrees with the selected Node reference on the complete snapshot domain |
| 1 | DIFFERENCES | Valid snapshots have head/reference differences; per-case IDs and base categories are retained |
| 2 | FAIL_CLOSED | A provider, timeout, source binding, output or input contract failed |

A matching result is finite differential evidence, not a standard-conformance
verdict, upstream acceptance or a claim about other engine versions. When a base
is given, MATCH still refers to the head/reference pair; base differences remain
in the report. Node versions may disagree with other engines.

## Supply your own observable cases

The script must evaluate to a string from JSON.stringify containing 1..10,000
rows. Each row has a unique nonempty string `id`, a `result`, and optionally
`input`. IDs and supplied input records must match across providers. JSON object
key order is ignored; boolean and numeric values remain distinct. JSON has one
numeric category, so 1 and 1.0 compare numerically equal.

```javascript
(function () {
  return JSON.stringify([
    {id: "astral-length", input: [55357, 56898], result: "🙂".length},
    {id: "one-plus-one", result: 1 + 1}
  ]);
})()
```

Use explicit observables such as UTF-16 unit arrays when string representation
matters. JSON.stringify itself loses distinctions such as undefined properties,
NaN/Infinity and negative zero; encode those explicitly if they matter. The
transport rejects raw unpaired surrogate units rather than silently replacing
them during UTF-8 output; escaped units inside valid JSON remain supported.
Duplicate JSON object keys, duplicate/missing case IDs, changed input records and
non-JSON numeric constants fail closed.

Node runs the source in a new ECMAScript context without Node host APIs. The selected engine uses
its normal ECMAScript runtime. Supply trusted corpuses: time/output limits are
not a security sandbox. Scripts are limited to 1 MiB, each output stream to
8 MiB (monitored while running), execution to 1..60 seconds and individual build/
fetch steps to 120 seconds. Oversized output can exceed the threshold between
monitor checks before the process is stopped. On macOS and Linux, each step
stops its owned process group before reading captured output, even when the
leader has already exited. This also covers timeouts and interruptions. The
Windows task-tree cleanup path runs for a still-running leader and has not been
validated here.

## Review an unmerged head

Pass both the full expected SHA and its pull-request ref. The fetched ref must
resolve to exactly that SHA, so a changed PR head cannot silently change the
experiment:

```sh
python3 tools/compare_js.py --script your-corpus.js \
  --base a4bedf5f60003b671ef339bb51ed3bead879cab7 \
  --head 50641de6a5ed3523c4f9c86b4411e308f798fa78 \
  --head-ref refs/pull/785/head --out evidence/my-pr-review
```

The full [5,280-case review corpus](https://gist.github.com/kimjooyoon/001ef8bd40bca857508dae3da2618414)
can be reused as `your-corpus.js`. Repositories are deliberately restricted to
the two engine pairs above; `--node` selects an installed Node executable. `--base` is optional.
If base and head are identical, the built head observer and its snapshots are
reused; the base output files are labeled by `reused_head` in provider metadata. No automatic
upstream messages or scheduled runs are created.

CI verifies the driver by checking all 24 normalization snapshots against explicit
expected input/result arrays and requiring the 12 known differences. Its PASS
means the driver reproduced those observations, while the original report stays
DIFFERENCES. CI also checks the 54 Sobek observations and the three corrected
cases, including explicit non-callable controls. Neither native report is changed
to manufacture PASS. The existing single 12-minute job and 7-day retention policy remain.
This native driver adds no claim that Gooo Text represents lone surrogates.
