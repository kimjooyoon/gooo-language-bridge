# Check integer parsing on a 32 bit Go target

`ToInt64E("9223372036854775807")` returned a range error in the recorded
Linux/386 Cast base, despite the input fitting `int64`. Its string parser used
the native `int` width before converting the result to the requested type.
Choose the parser width for the destination type. [Cast issue 310](https://github.com/spf13/cast/issues/310)
and the maintainer's [request for actual 32 bit execution](https://github.com/spf13/cast/issues/310#issuecomment-3397822985)
provide a concrete example of checking that decision while keeping the original
failures.

## Match the parser width to the destination

The final argument to [`strconv.ParseInt`](https://pkg.go.dev/strconv@go1.27.3#ParseInt)
selects the accepted integer width. Zero selects native `int`, even though
the function returns `int64`. Native `int` and `uint` have architecture dependent
widths, while `int64` and `uint64` always have 64 bits.
See the [Go numeric types specification](https://go.dev/ref/spec#Numeric_types).

The [original Cast helpers](https://github.com/spf13/cast/blob/fc670a425e3a64c4e872fa732cf0b6971e4dcbdb/number.go#L407)
used zero for that width in both signed and unsigned string parsing. A later
conversion to a wider type cannot undo an earlier range error.
The [proposal's parser selection](https://github.com/spf13/cast/blob/9b5719a3d52e3d211cf6baaba423da07c1e39da9/number.go#L377)
uses 64 for the 64 bit destinations, `strconv.IntSize` for native `int`/`uint`,
and the corresponding width for narrower destinations. Making every parser
accept 64 bits would lose the intended range check for native 32 bit values.

## Compare the same inputs on both sources

The [recorded execution](https://github.com/kimjooyoon/gooo-language-bridge/actions/runs/40202584288/job/121196691797)
ran upstream `TestNumber` and the same injected probe on these immutable sources:

- Base: `fc670a425e3a64c4e872fa732cf0b6971e4dcbdb`.
- PR 315: `9b5719a3d52e3d211cf6baaba423da07c1e39da9`, by `sagikazarmark`.

Both processes reported **Go 1.27.3, Linux/386, 32 bit `int`** from inside a
running test. These are the nine additional string conversions:

| API | String input | Base result | PR result |
| --- | --- | --- | --- |
| `ToIntE` | `-2147483648` | accept | accept |
| `ToIntE` | `2147483647` | accept | accept |
| `ToIntE` | `2147483648` | reject | reject |
| `ToIntE` | `-2147483649` | reject | reject |
| `ToUintE` | `4294967295` | accept | accept |
| `ToUintE` | `4294967296` | reject | reject |
| `ToInt64E` | `-9223372036854775808` | range error | accept |
| `ToInt64E` | `9223372036854775807` | range error | accept |
| `ToUint64E` | `18446744073709551615` | range error | accept |

Accepted results equal the input integer exactly. A rejected conversion must
return an error. Upstream `TestNumber` also fails on the base and passes on the
proposal. Neither selected execution skipped tests. These observations cover
the selected string boundaries and upstream numeric cases on Linux/386;
armhf and other toolchains were not executed.

## Read the capture before running again

The [frozen evidence packet](https://gist.github.com/kimjooyoon/b915d3701a02a7810c20d039cdf629d3/4f87b3e6eb3d71c466f62a2acf66aa1c6d90548a)
contains the probe, capture program, per-case results and source hashes.
`native-capture.tar.gz.base64.txt` preserves all 26 original files, including
the complete Go JSON output and stderr. Decode the Base64 text, then extract
the gzip tar archive; `manifest.json` lists each original file's SHA256.
You can inspect these saved results without installing Go or Gooo.

For a new execution, use a Linux host that supports 386 binaries and has
Go 1.27.3 installed. The capture uses the installed toolchain, fetches the two
pinned Cast sources and their Go dependencies, and removes temporary checkouts
after saving the results. It does not install a Go toolchain.

```sh
git init cast-386-observation
cd cast-386-observation
git fetch --depth=1 https://github.com/kimjooyoon/gooo-language-bridge.git 020db8bb203f5daaaa90042cd3de209d057c3c76
git checkout --detach 020db8bb203f5daaaa90042cd3de209d057c3c76
python3 tools/verify_cast_386.py
```

Open `native-observations/cast-310-386/observation.json`. `OBSERVED` means both
executions produced the required runtime witness and complete selected results.
Read each `go_exit_code`, `tests` and `bounds` entry to determine the semantic
outcome: this capture intentionally retains the base's nonzero exit.
A missing runtime witness or incomplete result produces `FAILED_INCOMPLETE`
with the original partial logs. Each run needs a fresh output directory;
choose another path with `--output` when repeating it.

## Adapt the method to a maintainer request

Keep the requested architecture, smallest relevant inputs and exact source
revisions together. Prove the target process actually ran: setting `GOARCH`
or successfully compiling a binary alone does not show its runtime behavior.
Check both the values a fix should accept and the overflows it must reject.
Report named cases rather than counting nested Go parent/package events as
independent tests.

The [result was delivered to the existing request](https://github.com/spf13/cast/issues/310#issuecomment-6398993053)
without opening a competing fix PR. The original implementation and proposal
belong to Cast; this Codex-assisted contribution supplied execution evidence.
The captured test result establishes neither maintainer acceptance nor a
Gooo compatibility claim. For your own report, follow the upstream contribution
policy and [check related work](contribution-candidate-check.md) before posting.
