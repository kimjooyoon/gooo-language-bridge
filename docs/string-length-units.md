# String length across Go, Python and JavaScript

A text limit expressed as “10 characters” is underspecified. Even before
grapheme clusters and terminal width, bytes, code points and UTF-16 units can
give three different counts for the same string.

| Input | UTF-8 bytes | Code points | UTF-16 units |
| --- | ---: | ---: | ---: |
| `gooo` | 4 | 4 | 4 |
| `가` | 3 | 1 | 1 |
| `🙂` | 4 | 1 | 2 |
| `e` followed by U+0301 | 3 | 2 | 2 |
| `👩` + U+200D + `💻` | 11 | 3 | 5 |

The Go, Python and Node.js operations below are independently executed on the same
decoded input; the table entries are also in the runnable corpus.

| Unit | Go | Python | JavaScript (Node.js) |
| --- | --- | --- | --- |
| UTF-8 bytes | `len(s)` for this valid UTF-8 domain | `len(s.encode('utf-8'))` | `new TextEncoder().encode(s).length` |
| Code points | `utf8.RuneCountInString(s)` | `len(s)` | `Array.from(s).length` |
| UTF-16 units | `len(utf16.Encode([]rune(s)))` | `len(s.encode('utf-16-le')) // 2` | `s.length` |

Go strings are byte sequences, and [the specification defines their length in
bytes](https://go.dev/ref/spec#String_types). Python [`str` is a sequence of
Unicode code points](https://docs.python.org/3.13/library/stdtypes.html#text-sequence-type-str).
The Go [`unicode/utf8`](https://pkg.go.dev/unicode/utf8#RuneCountInString) and
[`unicode/utf16`](https://pkg.go.dev/unicode/utf16#Encode) library operations give
the other counts. Explicit little-endian Python encoding avoids including a BOM.
JavaScript strings contain [UTF-16 code units](https://tc39.es/ecma262/multipage/ecmascript-data-types-and-values.html#sec-ecmascript-language-types-string-type);
`length` counts those units while the string iterator yields code points.
Node.js [TextEncoder](https://github.com/nodejs/node/blob/bd96dfbf0361576724b65322046e2ca9f9609cb9/doc/api/util.md#class-utiltextencoder)
encodes UTF-8. The adapter rejects lone surrogates before encoding can replace
them, preserving this bridge's scalar-string domain.

## Keep GoAWK positions in one mode

When applying the same unit choice in AWK, start with
[GoAWK's accepted Unicode guide](https://github.com/benhoyt/goawk/blob/592620f9bdce8a2fb9abb3ba5d4cfc1014e20375/docs/unicode.md).
By default, `length()`, `index()`, `match()`'s `RSTART` and `RLENGTH`, and
`substr()` use byte counts or positions. Choose `goawk -c` or
`interp.Config.Chars` for Unicode character counts and positions. Keep a
position from `index()` or `match()` in the same mode when passing it to
`substr()`.

Regexps use UTF-8 in either mode: matching one character with `/^.$/` does not
imply a byte length of one. The guide's `╋` example has length and matched length
3 in byte mode, or 1 in character mode; the regexp matches in both. For the
original executions, see the
[two byte/character-mode examples and their test limits](https://gist.github.com/kimjooyoon/6d6855f852800045a22e3db0a3d94ff5/871a8d5f75acf3ef6dc64251264c5a814e9fa4fb).
The guide also documents exceptions such as `printf`'s `%s` width and precision.

This is guidance for using GoAWK; GoAWK is not part of the 27-case comparison
below, and character mode does not establish grapheme or display-width counts.

## Give the unit an identity in Gooo

The [activity](../bridges/text-length/main.gooo) takes one Text and returns a
record with independently named fields:

```gooo
entity Lengths id "urn:gooo:bridge:text:lengths" fields {
    field utf8_bytes id "urn:gooo:bridge:text:utf8-bytes" type integer required one
    field code_points id "urn:gooo:bridge:text:code-points" type integer required one
    field utf16_units id "urn:gooo:bridge:text:utf16-units" type integer required one
}
```

The `urn:gooo:bridge:text:measure` activity counts UTF-8 leading bytes, adding a
second UTF-16 unit for a four-byte sequence. It does not call any native
reference implementation. Its counted loop and the compiler Text input limit
both stop at 1024 bytes. UTF-8 validity is a precondition, not a claim that the
leading-byte counter can validate arbitrary byte strings.

The verifier checks the original Gooo delivery's activity identity, input text,
actual record and each field's stable ID and integer value. Consequently an
equal total in a mislabeled field does not establish the intended observation.

## Run the comparison

From the repository root, after installing the pinned compiler as described in
the [README](../README.md):

```sh
python3 tools/compare_text_length.py --gooo .bin/gooo
```

Use Node.js 22.23.1, matching the pinned CI runtime. This executes one native Go
batch, one Node.js batch, one 27-case Gooo batch and a separate Gooo over-limit
rejection check. Python supplies independently calculated expectations. Three
additional Node.js controls must reject lone high/low surrogates and a 1025-byte
input with empty standard output and an explicit diagnostic.

All 27 records agree across the four implementations: 21 inputs distinguish bytes
from code points and 8 distinguish code points from UTF-16 units. Runtime identities
and wall time are recorded per run; these finite observations are not a performance
guarantee or proof over every string.

Inspect `evidence/text-length/rows.json` for all inputs and the four observed
records. `execution.stdout` is the original Gooo receipt, `go.stdout` the native
Go output, `javascript.stdout` the Node.js runtime identity and observations, and
`over-limit.stdout` the rejection of a 1025-byte input. The `javascript-*.stderr` files retain
the three negative-control diagnostics. Receipt digests bind the case document and workspace manifest; `summary.json` records
source/log hashes, runtime versions, exit codes and the GitHub execution context
when available. CI retains these artifacts for seven days, including on failure.
Hashes bind content and do not themselves establish author identity.

## What this comparison excludes

The fixed corpus covers empty and NUL strings, CRLF, Korean, accents, combining
sequences, emoji, ZWJ, variation selectors, Unicode encoding boundaries and
strings at 1023/1024 UTF-8 bytes. U+FFFD is tested as an ordinary valid scalar.
Malformed UTF-8 and lone surrogate code points are excluded. Go can store
arbitrary bytes; Python and JavaScript can represent lone surrogates. Those broader
domains are not equivalent to this bridge's Text domain.

No normalization is performed: precomposed `é` and `e` + U+0301 stay different
inputs. No field counts grapheme clusters, visual characters or terminal columns.
These 27 observations do not prove correctness over all Unicode strings or
complete Go/Python/JavaScript equivalence. No browser engine is executed. A UI
character limit needs a separately specified unit and may need grapheme segmentation beyond these three counts.

Pinned documentation source revisions and licenses are in
[provenance.json](../bridges/text-length/provenance.json). Code and corpus were
independently authored; executing runtime identities are observed separately.
The [proposal](https://github.com/kimjooyoon/gooo-language-bridge/issues/8) records
the bounded scope. This owned artifact does not count as upstream acceptance.
