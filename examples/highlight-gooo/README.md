# Highlight Gooo with a published Chroma release

This small CLI loads the submitted Gooo XML lexer into **Chroma v2.27.0**,
a pinned public release. You can use it before the lexer is accepted upstream.
It needs **Go 1.25+**; it does not need a Gooo compiler, model, browser service or
forked Chroma build. The bundled lexer is bound to the exact submission in
[provenance.json](provenance.json).

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

```sh
go -C examples/highlight-gooo test -race ./...
```

Tests cover Unicode and raw-string boundaries, all three line-ending forms,
HTML escaping, output failures, input limits and the bundled lexer hash.
The workbench's independent Chroma verifier also compares the XML bytes with
the exact submitted commit. Passing this consumer's tests does not mean
[upstream PR #1410](https://github.com/alecthomas/chroma/pull/1410) is accepted.
