# Missing, null and numeric defaults in HCL and Gooo

A missing field, an explicit `null` and an explicit zero have different meanings.
This bridge expresses that distinction with separate semantic field identities,
then compares actual Gooo deliveries with released HCL public API observations.

## Observe the native policy first

The [independent native observer](../examples/hcl-defaults-reference/README.md)
uses HCL v2.24.0 at commit `6b5068090eef06b1f127f61529db5ba0be7ed343`:

`TypeConstraintWithDefaults -> Defaults.Apply -> cty object conversion`

Four fixed constraints over the numeric attribute `v`, each with five inputs,
produce twenty distinct requests:

| Declaration | Missing | Explicit null | `-1` | `0` | `2` |
| --- | --- | --- | --- | --- | --- |
| Required number | Conversion error | null | -1 | 0 | 2 |
| Optional number | null | null | -1 | 0 | 2 |
| Optional number, default 0 | 0 | 0 | -1 | 0 | 2 |
| Optional number, default 42 | 42 | 42 | -1 | 0 | 2 |

Thus 19 inputs are accepted and one is an expected required-missing rejection.
Three accepted results are null. Four missing/null inputs acquire a default.
An explicit zero overrides 42; a zero default produces a non-null result.
A required attribute can hold an explicit null here: this experiment does not
impose an additional application-level non-null constraint.

Retained JSON records the actual cty object before defaults, after defaults,
and after conversion, plus the original diagnostic on rejection. A rejected
input is a successful observation, not a failed observer process. The driver
separately rejects six malformed adapter inputs with exit 2.

The source identity and checksum are pinned in
[provenance.json](../bridges/hcl-null-defaults/provenance.json). HCL remains
MPL-2.0; the independently authored observer and Gooo activity are MIT. This
behavior is in the released base. It does not depend on the unmerged
[TypeString proposal](hcl-type-roundtrip.md), whose separate default-value
boundary motivated this question.

## Express intent with Gooo identities

The [activity](../bridges/hcl-null-defaults/main.gooo) has ID
`urn:gooo:bridge:hcl-defaults:resolve`. Its request and result field IDs have
prefix `urn:gooo:bridge:hcl-defaults:`:

| Field | Stable ID suffix | Meaning |
| --- | --- | --- |
| `is_optional` | `is-optional` | Declaration permits omission |
| `default_present` | `default-present` | A non-null numeric default is declared |
| `default_value` | `default-value` | Default payload, including zero |
| `provided` | `provided` | The input object contains the attribute |
| `input_null` | `input-null` | Its supplied value is null |
| `input_value` | `input-value` | Supplied numeric payload |
| `accepted` | `accepted` | Conversion accepts this request |
| `is_null` | `is-null` | An accepted result is null |
| `value` | `value` | Payload of an accepted non-null result |

Null and missing are represented through typed flags; they are not encoded as
zero. The integer payload is canonical zero for null/rejected results and has
no value meaning in those results. `accepted=false` distinguishes rejection
from an accepted null. Inspect all fields together.

Valid compared requests derive from the four native declarations and five
input states. A default implies an optional declaration. Missing input has
`provided=false`, `input_null=false`, `input_value=0`; explicit null has
`provided=true`, `input_null=true`, `input_value=0`. Unused default payloads
are zero. These relational domain constraints define the corpus; the Gooo
entity enforces required field types, not every relationship among the flags.
Arbitrary flag combinations are not certified HCL inputs.

## Run the comparison

Follow the [compiler setup](../README.md#reproduce-the-semantic-comparisons), then:

```sh
python3 tools/verify_hcl_defaults.py --gooo .bin/gooo
```

The verifier pins module Origin.Hash/checksum, checks module integrity, retains
source/license/runtime identity and original native output, and derives Gooo
case expectations from the validated native projection. A separate Python
policy validates native observations. It checks complete receipt counts,
case indices, activity ID, typed inputs/outputs, stable field IDs and the
cases/manifest digests. Retained Gooo values come from actual deliveries.
Two wrong-type requests and a missing presence flag must fail input validation.

Inspect `evidence/hcl-null-defaults/summary.json`, `native.stdout`, `rows.json`,
`cases.json`, `execution.stdout` and the rejection receipts. Hash references
bind captured files and source. The existing single bounded Linux CI job runs
this verifier before the [offline evidence audit](audit-ci-evidence.md).

## Keep the scope explicit

Only inputs -1/0/2 and defaults 0/42 are compared. This does not model arbitrary
precision, fractions, strings/booleans as numeric values, multiple attributes,
dynamic/unknown cty values, nullable defaults or arbitrary HCL constraints.
The adapter's protocol bounds do not restrict HCL's general language semantics.

The [Tengo bridge](input-defaults.md) models map overrides and rejects null at
its adapter boundary. Its missing-field policy is a different observation;
sharing a default-related word does not make those language behaviors equal.
The HCL bridge neither compiles HCL through Gooo nor claims general language
conformance, performance, upstream acceptance or adoption.
