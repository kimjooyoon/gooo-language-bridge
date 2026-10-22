# Native Tengo defaults observer

Execute a fixed Tengo map-override script through the public Script/Compiled APIs.
No Gooo compiler is needed for this native-only command, from the repository root:

```sh
printf '%s\n' '[{"id":"zero-false","overrides":{"b":0,"enabled":false}}]' | GOWORK=off GOTOOLCHAIN=go1.27.3 go -C examples/tengo-defaults-reference run .
GOWORK=off GOTOOLCHAIN=go1.27.3 go -C examples/tengo-defaults-reference run . --identity
```

The first command reports `actual` settings `a=0`, `b=0`, `enabled=false`.
An empty override map yields defaults 0, 1, true. A batch compiles once and reuses
that same Compiled object; the script creates a new settings map for every run.
`--identity` records the actual Go/dependency identity and the compiled Tengo
source. Go can download the pinned toolchain and module; no model, API key or
paid service is used.

Input is one JSON array of 1..64 cases, at most 64 KiB. Each case has a unique
nonempty ID (up to 64 bytes) and an `overrides` object. Keys are limited to `a`,
`b` and `enabled`; values must be int64, int64 and Boolean respectively. Null,
unknown keys and wrong types are rejected by this observer before executing the
script. These are adapter bounds, not restrictions on Tengo's general map type.
Output is emitted only after the whole batch succeeds. Go's standard JSON decoder
is used; this is not a generic duplicate-property validator.

The dependency is original source `18239400d1ee45940e4cb881e2e9840cb916d0f6`,
module `v2.17.1-0.20261013061022-18239400d1ee`, checksum
`h1:LW99H2y+9r/3ZHsNiLlqYwyPqRlB/ExxyhWin9AI5QU=`. That is a development
pseudo-version, not released v2.17.1. The observer is independently authored under
the workbench's MIT license; upstream Tengo remains MIT licensed. No engine
implementation is copied.

The [native/Gooo comparison guide](../../docs/input-defaults.md) describes the
48 unique maps, stable semantic IDs, explicit zero/false observations, reuse
transitions and exclusions. The comparison driver checks the canonical module
Origin, module verification, built identity and original outputs; it retains
observer/module/source files and the upstream license. Build/module steps have
120-second timeouts; native execution has 30 seconds. The shared process monitor
limits each stream to 8 MiB with possible monitoring overshoot; it is not a memory
sandbox. Each run records its actual platform. The comparison is configured for the
existing Linux CI job; inspect its result before claiming Linux validation.
Windows execution and whole-language conformance are outside this experiment.
