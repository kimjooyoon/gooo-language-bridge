# Defaults depend on presence, not truthiness

An explicit `0` or `false` can be a useful override. It should not silently select
a default just because it is falsy. This experiment gives presence its own Gooo
field identity and compares the resulting settings with an independently
executed Tengo script.

The practical starting point is [Tengo question #471](https://github.com/d5/tengo/issues/471)
and the [submitted documentation example #496](https://github.com/d5/tengo/pull/496).
That documentation demonstrates two integer settings. This workbench adds a
Boolean setting to examine explicit false; it is an independent extension, not
another upstream patch or a claim the documentation has been accepted.

## Native behavior

The pinned Tengo runtime executes this fixed source:

```tengo
settings := {a: 0, b: 1, enabled: true}
for key, value in overrides {
    settings[key] = value
}
resolved_a := settings.a
resolved_b := settings.b
resolved_enabled := settings.enabled
```

The Go host registers one `overrides` global, compiles once and replaces that
map before each `Run`. The script constructs a fresh defaults map on every run.
The observer checks actual `Variable.Value()` types rather than using conversion
helpers that could hide a wrong value as zero. The foreign keys `a`, `b` and
`enabled` are the adapter's declared mapping, not global identifiers discovered
automatically by either language.

| Overrides | Resolved settings |
| --- | --- |
| `{}` | `{a: 0, b: 1, enabled: true}` |
| `{b: 0, enabled: false}` | `{a: 0, b: 0, enabled: false}` |
| `{a: -1}` | `{a: -1, b: 1, enabled: true}` |

These rows are examples from a 48-map corpus. Each integer field is absent or
has one of -1, 0, 2; the Boolean field is absent, false or true. Thus 4 × 4 × 3
is **48 distinct native input maps**, without duplicated missing-value variants.
Ordering deliberately puts missing fields after non-default values: the current
sequence observes resets for `a`, `b` and `enabled`. Reset-transition counts are
observations within the corpus, not additional Gooo cases or a proof about all
possible execution histories.

## Gooo's independent intent

The [activity source](../bridges/input-defaults/main.gooo) takes six required
fields. Each native key maps to a `*_present` Boolean and a separate typed
`*_value`. Missing integer values are canonically represented as 0, and a missing
Boolean value as false; the presence field decides whether the value is used.
For `{b: 0, enabled: false}`, `b_present` and `enabled_present` are true even
though their values are falsy. `a_present` is false.

For example, the native key `b` maps to stable IDs
`urn:gooo:bridge:defaults:b-present` and `urn:gooo:bridge:defaults:b-value`.
The returned setting has ID `urn:gooo:bridge:defaults:resolved-b`; the activity
has ID `urn:gooo:bridge:defaults:resolve`. The receipt retains all six input and
three output field identities and typed values. Renaming a native key would
require an adapter change; this experiment does not establish automatic schema
matching.

Gooo starts with defaults for each invocation and conditionally selects the
provided values. It does not run Tengo or parse its source. Tengo supplies
independent runtime observations from its map-copy pattern, while the Gooo
activity expresses the typed presence policy. The Gooo side is a stateless
operation; this does not introduce a general shared-state model or prove state
isolation for arbitrary programs.

## Run and inspect

Install the [pinned compiler and runtimes](../README.md#reproduce-the-semantic-comparisons),
then run from the repository root:

```sh
python3 tools/verify_input_defaults.py --gooo .bin/gooo
```

A successful run requires all 48 native and Gooo outputs to match. It also
requires five native-observer rejections (null, Boolean-as-integer,
integer-as-Boolean, unknown key and duplicate case ID) and three Gooo field-type
rejections plus a required-presence-field rejection. Native failures must exit 2 with empty stdout and the expected
single-line diagnostic. Gooo failures must be source/case-bound
`FAIL_CLOSED` receipts at input validation.

Those native checks are **this observer's input contract**, not new Tengo
language restrictions: Tengo can represent undefined and other map values,
which are outside this typed comparison. No floats, nested maps, null,
unknown fields, arbitrary-precision compatibility, general compiler equivalence
or upstream acceptance is claimed.

`evidence/input-defaults/` retains the input order, exact source/module/license,
module download identity and verification output, native runtime identity and
original JSON, Gooo cases/compiler/receipt, rejection receipts and matched rows.
Each source, receipt, case index, field ID and Boolean/integer type is checked.
The summary records 48 unique maps and the observed reset transitions. Binary
hashes are metadata; the built native observer is temporary.

The module is pinned to original Tengo source
`18239400d1ee45940e4cb881e2e9840cb916d0f6`, development pseudo-version
`v2.17.1-0.20261013061022-18239400d1ee` (not released v2.17.1).
[Provenance](../bridges/input-defaults/provenance.json) records the checksum,
executed script and MIT licensing context. No Tengo implementation was copied
into the bridge, and no Gooo dependency was added upstream.

For a native-only run, see the [standalone observer](../examples/tengo-defaults-reference/README.md).
The existing single bounded CI job runs the comparison and preserves its output;
passing it establishes only the stated finite observations.
