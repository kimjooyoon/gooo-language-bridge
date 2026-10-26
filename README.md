# go-toml PR 1137: pointer/interface cycle still bypasses the depth guard

On PR head `ad54769aba4d63f437e1df88bd9bc16072fd00e7`, default `Marshal` still loops on a pointer/interface cycle inside an otherwise supported map:

```go
var value interface{}
value = &value
_, err := toml.Marshal(map[string]interface{}{"self": value})
```

This is a remaining case in the cycle-prevention fix for [issue 1136](https://github.com/pelletier/go-toml/issues/1136), not a claim that [PR 1137](https://github.com/pelletier/go-toml/pull/1137) introduced it. The input must be constructed by Go code; it is not a TOML-text decoding exploit.

Observed on 2026-10-26 using Go 1.27.3, darwin/arm64, 64-bit int. The observer emitted its call-start record and did not emit a returned record before the supervisor deadline. The configured deadline was 0.75 seconds from subprocess startup; SIGQUIT was actually sent at 0.826525 seconds and the process was reaped at 0.891999 seconds. Its captured stack was `resolve` at marshaler.go:435, called by `isTableLike`, `entryIsTable`, and `encodeTableEntries`. Exit 2 is caused by the diagnostic signal, not an error returned by the library.

| Control on the same PR head | Observed |
| --- | --- |
| Ordinary map | Returns and round-trips `answer = 7` |
| Self-referencing map | Returns the proposed cycle/depth error |
| Two entries sharing one acyclic pointer | Returns and round-trips both `a = 7` and `b = 7` |
| Nil interface and interface-held typed-nil pointer | Omits the nil interface; encodes the typed-nil pointer as zero |

Source inspection explains the difference: [resolve](https://github.com/pelletier/go-toml/blob/ad54769aba4d63f437e1df88bd9bc16072fd00e7/marshaler.go#L423) repeatedly unwraps Ptr/Interface without re-entering a guarded container. With tables-inline enabled, [appendValue](https://github.com/pelletier/go-toml/blob/ad54769aba4d63f437e1df88bd9bc16072fd00e7/marshaler.go#L1607) recursively unwraps the same pair. The inline-cycle path was inspected only, not executed.

A fix should cover unwrapping during classification and value encoding while preserving shared acyclic aliases. A global permanent set of all previously seen pointers would reject valid sharing. No production patch is supplied here.

## Evidence and replay

`observer.go` is the exact compiled probe; `run_observation.py` is the exact external supervisor; `observation.json` records arguments, environment, outcomes and source hashes. `validation.json` and `validate_observation.py` separately check the expected outcomes; supervisor completion alone is not a test pass. All 122 tracked source files matched their pinned Git blobs before and after execution. The observer, injected copy, supervisor and binary hashes were checked after execution.

`raw-logs.tar.gz.base64.txt` preserves all preparation and observation stdout/stderr files, including empty files. Decode Base64, decompress gzip, then read the tar members. `manifest.json` gives the byte count and SHA-256 of each member and each other packet file. No log text has been removed or rewritten.

To replay, prepare a fresh checkout of the exact PR head in a `source` directory next to these files, place `observer.go` at `source/gooo-review-observer/main.go`, and point the supervisor's SDK constant to an installed compatible Go toolchain. Use a fresh output directory without `observation.json` and execute `python3 -B run_observation.py`. The supervisor uses a single build and a separate process group for each case, writes output to files, and terminates/reaps timed-out processes. Do not run the cyclic probe without an external process deadline. Any replay is a new observation with its own time and hashes; do not overwrite the original record.

The Go memory target is a soft 32 MiB target, not a hard memory cap. A separate maximum goroutine stack size is 8 MiB. The external supervisor enforces termination. No baseline cycle or inline cycle was executed. Build/version/five probe subprocesses took 4.141543 seconds combined. This is a focused review observation, not full-suite, race, coverage, benchmark, fuzz, capability or CI acceptance evidence. AI-assisted source review and experiment preparation.
