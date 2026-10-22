# Native GoLua integer floor observations

This small Go host compiles and executes the Lua chunk `local a, b = ...; return a // b`
through the public [GoLua runtime](https://github.com/arnodel/golua). It does not
compute the quotient in Go. The dependency is pinned to original source
`3b0306a844cbc263da253ee0503997dfe85d4cc1`, module
`v0.4.1-0.20261014212727-3b0306a844cb`; this development pseudo-version is not a
released v0.4.1. [Provenance](provenance.json) records the full revision, checksum,
license, executed Lua source and scope. GoLua is an implementation of Lua 5.5;
this observer does not run the official C implementation.

From the repository root, no Gooo compiler or separate Lua executable is needed
for this native-only observation:

```sh
printf '%s\n' '[{"a":-7,"b":3}]' | GOTOOLCHAIN=go1.27.3 go -C examples/lua-division-reference run .
GOTOOLCHAIN=go1.27.3 go -C examples/lua-division-reference run . --identity
```

The first command emits `[{"a":-7,"b":3,"quotient":-3}]`. The second records the
actual Go runtime and dependency version/checksum. Go may download the pinned
module/toolchain; there is no model, API key or paid runner.

Input is exactly one JSON array of 1..128 pairs, at most 64 KiB, with required
int64 `a` and `b` fields. Unknown fields, non-integers, overflow and additional
JSON values are rejected. Each fixed arithmetic call runs in a GoLua context
with 10,000 CPU units and a 1 MiB accounting limit. Successful rows contain an
integer quotient; Lua errors are retained in `error`. The host process bounds
and output retention used by the full comparison are documented below.

## Join the existing Gooo activity

```sh
python3 tools/compare_division.py --gooo .bin/gooo
```

The comparison runs the existing 120 Go/Python/Gooo cases and joins independent
GoLua observations by exact input pair. Python and the actual Gooo delivery
match all 120 GoLua quotients on dividends -7..7 and nonzero divisors -4..4.
Native Go truncation differs on 30 of those inputs. The Gooo activity keeps its
existing Python floor-intent ID; matching a bounded subset does not rename its
identity or establish general Lua/Python integer equivalence.

Three **excluded** native cases are retained separately:

| Input | GoLua result | Python result |
| --- | --- | --- |
| -9223372036854775808 // -1 | -9223372036854775808 | 9223372036854775808 |
| 9223372036854775807 // 1 | 9223372036854775807 | 9223372036854775807 |
| 1 // 0 | Lua divide-by-zero error | ZeroDivisionError |

The first demonstrates GoLua int64 wrapping versus Python's unbounded integer.
The maximum-integer row is a control. The error row does not assert equivalent
exception types. Large values are additionally recorded as decimal strings in
`lua-edge-rows.json` to prevent lossy display through a binary64 JSON reader.
None of these three inputs is submitted to Gooo or counted as a Gooo match.
[Lua's numeric representation and overflow rules](https://www.lua.org/manual/5.5/manual.html#2.1)
and [arithmetic operators](https://www.lua.org/manual/5.5/manual.html#3.4.1) describe
the language contract; the actual implementation/source observed here remains
explicit in the report.

`evidence/division-comparison/` retains the compiled observer's source/module
files, module download identity (including full source revision), build and
execution stdout/stderr, input arrays, original GoLua outputs, boundary records
and enriched `rows.json`. Three malformed-input controls independently require
exit 2, empty stdout and the expected diagnostic for a missing operand, int64
overflow and a trailing JSON value. Its summary records source/file/binary hashes and the
runtime identity. Each build/module step is limited to 120 seconds, each native
execution to 30 seconds, with the shared driver's 8 MiB per-stream process
monitor. Monitoring can overshoot before stopping a process; it is not an OS
memory sandbox. Native validation covers macOS and Linux, not Windows.

The observer is independently authored under this repository's MIT license;
GoLua retains Apache-2.0. No upstream implementation was copied. No floats,
metamethods, arbitrary-precision compatibility, performance comparison, whole
language conformance or acceptance of an upstream patch is claimed.
