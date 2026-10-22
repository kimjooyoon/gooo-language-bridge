# Native HCL missing/null/default observer

Run released HCL public APIs without a Gooo compiler. The source-pinned module
is HCL v2.24.0, commit `6b5068090eef06b1f127f61529db5ba0be7ed343`, MPL-2.0.
The observer is independently authored under this workbench's MIT license.
No engine implementation is copied and no upstream CLA is signed.

From the repository root, generate the bounded input file and run:

```sh
python3 -c 'import json; from tools.verify_hcl_defaults import corpus,native_inputs; print(json.dumps(native_inputs(corpus())))' > /tmp/hcl-defaults-inputs.json
GOTOOLCHAIN=go1.27.3 GOWORK=off go -C examples/hcl-defaults-reference run . --input /tmp/hcl-defaults-inputs.json
GOTOOLCHAIN=go1.27.3 GOWORK=off go -C examples/hcl-defaults-reference run . --identity
```

Each row calls `TypeConstraintWithDefaults`, `Defaults.Apply` where present,
and cty object conversion. It records the original object, the object after
default application, the converted result or original conversion diagnostic,
and a typed projection (`accepted`, `is_null`, `value`). A required missing
attribute is an expected observation, so the observer command still exits zero.

The four declaration labels select fixed constraints: required number, optional
number, optional number with default zero, and optional number with default 42.
The state is `missing`, `null`, or `number`. The numeric payload must be present
as an int64 and must be canonical zero for missing/null; `state:null` represents
an actual typed HCL null, not a null numeric JSON payload. Retained `input` JSON
comes from the actual cty input value. Input may be stdin or `--input FILE`;
`--identity` reports actual runtime/dependency identity and fixed constraints.

The adapter validates the entire batch before execution: 1..64 cases, 64 KiB,
unique nonempty IDs of at most 64 bytes, known fields/declarations/states,
int64 payloads and canonical unused payloads. Protocol failures exit 2 without
stdout. It does not claim to reject duplicate JSON object properties. Inputs
outside this adapter are not limitations of the HCL language.

[The bridge guide](../../docs/hcl-null-defaults.md) gives the 20-case matrix,
semantic identities, expected rejection and explicit-null boundaries. Only the
small integer corpus is compared with Gooo. General HCL numbers, arbitrary
constraints, multiple attributes, nullable defaults, dynamic values and general
HCL/Gooo equivalence are outside that comparison. Native-only input support
beyond the tested corpus is not certified compatibility.
