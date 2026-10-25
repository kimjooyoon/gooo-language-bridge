# Cast #310: Linux/386 observation

This one-time experiment on `observe/cast-310-linux-386` answers the
[maintainer's request for a 32-bit check](https://github.com/spf13/cast/issues/310#issuecomment-3397822985)
of existing [Cast PR #315](https://github.com/spf13/cast/pull/315).

The source pins are:

- Base: `fc670a425e3a64c4e872fa732cf0b6971e4dcbdb`.
- Proposal: `9b5719a3d52e3d211cf6baaba423da07c1e39da9`.

On Linux with Go 1.27.3 and support for executing 386 binaries, run:

```sh
python3 tools/verify_cast_386.py
```

Both revisions receive identical copies of `probe_test.go`. The selected tests
are upstream `TestNumber`, a runtime witness, and nine specific string-conversion
bounds: native `int` minimum/maximum/overflow/underflow, `uint` maximum/overflow,
and the `int64` minimum/maximum and `uint64` maximum. The compiled test process
must report Go 1.27.3, Linux, architecture `386`, and a 32-bit `int`.

Results are retained under `native-observations/cast-310-386/`: `observation.json`, raw
stdout/stderr, the injected probe, revision bindings and source hashes. The output
directory must be new; use `--output` with another fresh directory to retain a
separate attempt. CI uploads this capture as the separate
`cast-310-386-<github.sha>` artifact. The native capture checks its own bindings;
the existing Gooo evidence audit does not certify this packet.

A green CI result means the selected observations completed with the required
runtime witness. Semantic test failures on either revision remain recorded;
they are not converted into passing assertions. The evidence covers this
Linux/386 run only. Maintainer acceptance of the fix, armhf behavior and the full
platform/toolchain matrix remain unestablished.
