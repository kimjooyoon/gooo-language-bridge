# Your first native observation

You can contribute a small native JavaScript observation without installing Gooo
or writing a semantic bridge. Start by running this three-case example, then
change one observable behavior that matters to your own project. A useful new
counterexample is more valuable than a larger passing-case count.

## Run the example

Requires Python 3.9+, Git, Go and Node.js. The driver selects Go 1.27.3 and Go may
download that toolchain and module dependencies. No model or API key is used.
The recorded example used Node.js 22.23.1; the report records your actual Node
version, which may affect other experiments.

```sh
git clone https://github.com/kimjooyoon/gooo-language-bridge.git
cd gooo-language-bridge
python3 tools/compare_js.py --engine goja \
  --script examples/js-differential/first-observation.js \
  --head 64adc8bb4d51821549c138900ca6bc31194f403d \
  --out evidence/my-first-observation
```

Choose a fresh output directory each time. The example is expected to exit zero
and report `MATCH` with three cases. These are the individual observations:

| Case | Result | What the operation counts or computes |
| --- | ---: | --- |
| `utf16-length` | 2 | UTF-16 code units in `🙂` |
| `code-point-count` | 1 | Unicode code points in the same string |
| `negative-floor` | -3 | Floor of -7/3 |

This is agreement between the pinned Goja source and the selected Node runtime
on three cases. It does not execute Gooo, establish general language equivalence,
or show that a patch was accepted upstream. For the Gooo activities connected to
these concepts, see [string-length units](string-length-units.md) and
[integer floor division](python-go-integer-division.md).

## Read the evidence

Open `evidence/my-first-observation/report.json` for the source SHA/tree, engine,
runtime identities, original-output hashes and per-case classification. Compare
`node.stdout` with `head.stdout`; they contain the original snapshot JSON. The
report keeps `MATCH`, `DIFFERENCES` and `FAIL_CLOSED` separate:

- Exit 0: head agrees with Node on this snapshot domain.
- Exit 1: valid observations differ. Keep the case; a difference alone does not
  identify which runtime follows the relevant contract.
- Exit 2: execution, source binding or the snapshot contract failed. Keep stderr
  and repair the experiment before interpreting its output as a language result.

## Make one observation your own

Copy `first-observation.js` to a new file. Give each case a distinct `id`, preserve
its actual `input`, and return JSON.stringify of the rows. Change the input or
operation to reproduce your use case. See the [driver contract](../examples/js-differential/README.md#supply-your-own-observable-cases)
for typed results, limits and ways to represent values that JSON cannot preserve.
Supply trusted scripts: execution limits do not make this a security sandbox.

Pin the engine commit you tested. For an unmerged patch, pass its expected full
SHA and `--head-ref refs/pull/N/head`; a moved ref fails closed. Add `--base` when
comparing a proposed change, or select `--engine sobek` for Sobek. The
[54-observation Sobek example](../examples/js-differential/README.md#choose-an-engine)
credits its original patch author and demonstrates three corrected differences.

## Share a reproducible result

Before reporting, check existing work here and upstream. The included Goja
normalization and Sobek reviver corpuses already reproduce linked issues/PRs;
rerunning them is useful locally, but does not make them new bug reports.

Use the [native observation form](https://github.com/kimjooyoon/gooo-language-bridge/issues/new?template=native-observation.yml)
for a new result: include a minimal script, exact source, relevant runtime
identity, the observed/expected values, and links to the contract and related
work. State what you did not test. Share the smallest useful original-output
excerpt or a durable reproduction link; complete reports are not prerequisites
for asking a focused question.

A native observation does **not** require a `.gooo` file. A new Gooo semantic
bridge does: it needs stable semantic IDs, an independent reference and a
bounded domain. [Contributing](../CONTRIBUTING.md) describes both paths. This
repository's CI cannot authorize an external project's PR or override its rules.
