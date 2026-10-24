# Highlight Gooo source

Create a self-contained HTML page so you can read a `.gooo` file with syntax
highlighting. Requires **Go 1.25+** and network access to fetch Go modules.

## Try the published version

Download [floor.gooo](https://github.com/kimjooyoon/gooo-language-bridge/releases/download/examples/highlight-gooo/v0.1.1/floor.gooo)
into your current directory, then run:

```sh
go run github.com/kimjooyoon/gooo-language-bridge/examples/highlight-gooo@v0.1.1 floor.gooo > floor.html
```

**Expected result:** `floor.html` contains the highlighted sample. Open it in a
browser; the page includes its styles and fetches no remote assets. The command
highlights source without executing it and needs no Gooo compiler.

## What is available now

The [published helper v0.1.1](https://github.com/kimjooyoon/gooo-language-bridge/releases/tag/examples/highlight-gooo/v0.1.1)
bundles the Gooo XML lexer and uses the released **Chroma v2.27.0** runtime.
The same lexer was [merged upstream](https://github.com/alecthomas/chroma/pull/1410)
on October 22, 2026, into **Chroma v3 development**. As checked on October 25,
no released Chroma tag includes Gooo yet; v2.27.0 does not discover Gooo by itself.
Use the helper above to highlight Gooo with that published runtime.

The [acceptance record](../../docs/observations/2026-10-25-chroma-accepted.json)
links the upstream merge and checks. [Source metadata](provenance.json) binds
the bundled XML to the accepted source. These records are separate from whether
a particular user has run the tool.

## Install a persistent command

```sh
go install github.com/kimjooyoon/gooo-language-bridge/examples/highlight-gooo@v0.1.1
highlight-gooo -format json floor.gooo
```

Go installs commands into `GOBIN`, or `$(go env GOPATH)/bin` when unset; that
directory must be on your `PATH`. `go run` avoids that setup. JSON token values
reconstruct the original valid UTF-8 source. The release also contains sample
HTML and JSON output.

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

## Verification details

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
the exact accepted source. Upstream acceptance is established by the merged PR
and its successful upstream checks, recorded in
[the dated acceptance record](../../docs/observations/2026-10-25-chroma-accepted.json).
Consumer tests establish their own behavior and source fidelity.
