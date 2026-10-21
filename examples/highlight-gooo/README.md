# Highlight Gooo with a published Chroma release

This small CLI loads the submitted Gooo XML lexer into **Chroma v2.27.0**,
a pinned public release. You can use it before the lexer is accepted upstream.
It needs **Go 1.25+**; it does not need a Gooo compiler, model, browser service or
forked Chroma build. The bundled lexer is bound to the exact submission in
[provenance.json](provenance.json).

## Try the published version without cloning

Download [floor.gooo](https://github.com/kimjooyoon/gooo-language-bridge/releases/download/examples/highlight-gooo/v0.1.1/floor.gooo)
from the [experimental v0.1.1 release](https://github.com/kimjooyoon/gooo-language-bridge/releases/tag/examples/highlight-gooo/v0.1.1),
then run with your Go installation:

```sh
go run github.com/kimjooyoon/gooo-language-bridge/examples/highlight-gooo@v0.1.1 floor.gooo > floor.html
```

Open `floor.html` in a browser. For a persistent command:

```sh
go install github.com/kimjooyoon/gooo-language-bridge/examples/highlight-gooo@v0.1.1
highlight-gooo -format json floor.gooo
```

Go installs commands into `GOBIN`, or `$(go env GOPATH)/bin` when unset; that
directory must be on your `PATH` to use the installed name. `go run` avoids this
setup. The release also includes sample HTML and JSON output. Installation from
the versioned module needs Go and network access; it does not execute the sample
as a Gooo program.

## From a checkout

From the repository root:

```sh
go -C examples/highlight-gooo run . ../../bridges/python-floor/main.gooo > floor.html
```

Open `floor.html` in a browser. The page includes its styles and escapes the
source as text; it fetches no remote assets. For source/token inspection:

```sh
go -C examples/highlight-gooo run . -format json ../../bridges/python-floor/main.gooo
```

Use `-` as the filename to read stdin. Concatenating the JSON token values
reconstructs the original valid UTF-8 input, including LF, CRLF and CR endings.
Gooo raw strings preserve those endings, so the consumer explicitly disables
Chroma's default line-ending normalization. Activity bodies remain raw strings.
The tool highlights lexical structure; it does not establish that a program is
well-typed, executable or syntactically complete.

Input is limited to 4 MiB. Unknown formats, invalid UTF-8, lexer Error tokens,
changed source text and write failures produce nonzero exits. The HTML output
is first buffered because the published formatter can swallow writer errors;
the final checked write retains a broken pipe or disk error.

Version 0.1.1 stops consuming raw tokens at the first lexer Error, before the
coalescer can read ahead across an invalid run, and reports that first raw token.
It writes no partial output. The input is still read within the existing 4 MiB
limit; this is an early lexical rejection, not streaming file input.

```sh
python3 tools/verify_highlighter.py
```

Verification uses the workbench's Python and Go 1.27.3 setup, and downloads the
Go 1.25.0 compatibility toolchain if missing. From the repository root, this
compares against the exact v0.1.0 source and keeps
the original measurements in `evidence/highlighter-first-error/`. It checks twelve
byte-identical valid HTML/JSON outputs, the first-error behavior, three single
benchmark iterations per version on a 128 KiB run of `?`, and compatibility tests
on Go 1.25.0. The allocation gate requires a reduction by more than half on that
specific input; execution timing is observational. `B/op` measures total allocated
bytes rather than peak memory. The current Go 1.27.3 race tests cover the same
consumer separately.

```sh
go -C examples/highlight-gooo test -race ./...
```

Tests cover Unicode and raw-string boundaries, all three line-ending forms,
HTML escaping, output failures, input limits and the bundled lexer hash.
The workbench's independent Chroma verifier also compares the XML bytes with
the exact submitted commit. Passing this consumer's tests does not mean
[upstream PR #1410](https://github.com/alecthomas/chroma/pull/1410) is accepted.
