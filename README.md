# go-toml PR 1129: preserve TextUnmarshaler precedence for named floats

The existing `TestIssue1109_TextUnmarshalerNamedScalarKinds/integer_into_float_kind` passes on base `686c980c47581bf19b6119b60e9a59f2aed04170` and fails on proposed head `1c141f3082a628d7a2115bbcaf03056351f83a5b`. Its named float's text decoder multiplies input by ten. For `V = 2`, the base yields 20 and the proposal yields 2 without an error.

The new successful integer-to-float branch sets the target and returns before the TextUnmarshaler check in `assignFloat`. That bypasses the precedence already covered by the existing regression for issue #1109. The existing hook should retain precedence over native conversion.

- [Proposed change](https://github.com/pelletier/go-toml/pull/1129)
- [Exact changed path](https://github.com/pelletier/go-toml/blob/1c141f3082a628d7a2115bbcaf03056351f83a5b/unmarshaler.go#L1755)
- [Existing named-float regression](https://github.com/pelletier/go-toml/blob/1c141f3082a628d7a2115bbcaf03056351f83a5b/unmarshaler_test.go#L6060)

## Observation

Run with installed Go 1.27.3, darwin/arm64, on 2026-10-26 UTC. Both checkouts and their tests were unmodified. The named-scalar test section is byte-identical between revisions. Each revision ran:

```sh
go test -count=1 -timeout=15s -p=2 -json -run '^(TestIssue1109_TextUnmarshalerNamedScalarKinds|TestUnmarshal_Floats)$' .
```

The base invocation passed. The PR invocation failed only the integer-into-float child case, its parent group and the package result. Both float groups passed, including the PR's added hexadecimal, octal and binary cases. Those prefixed cases are additions in the PR, not cases already present in the base. Neither invocation skipped tests or hit its deadline. This is one failing case, not three independent failures.

The supervisor limits each Go invocation to 45 seconds in a separate process group, with output written to files. Version and the two test calls took 2.995373 seconds combined. All process groups were closed. Module/toolchain downloads were disabled. Source bytes matched the pinned Git blobs before and after execution.

## Retained evidence

`observe.py` is the exact supervisor. `observation.json` records revisions, commands, environment, source hashes and results. `validation.json` checks the recorded scope and includes the failing output. `original-test-logs.tar.gz.base64.txt` contains all six original version/test stdout and stderr files, including empty stderr files. Decode Base64, decompress gzip, and read the tar members. `manifest.json` supplies byte counts and SHA-256 values for the packet and each log.

For a fresh replay, create clean `base` and `pr1129` checkouts at the recorded revisions beside the supervisor, point its SDK constant to an installed Go toolchain, and run `python3 -B observe.py` in a fresh output directory. Keep the original observation intact; a replay has its own timestamps and hashes.

This is a focused review observation. No new tests, production patch, full-suite/race/coverage/benchmark/capability acceptance, or maintainer acceptance are claimed. AI-assisted review and experiment preparation.
