# String length across Go and Python

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

The Go and Python operations below are independently executed on the same
decoded input; the table entries are also in the runnable corpus.

| Unit | Go | Python |
| --- | --- | --- |
| UTF-8 bytes | `len(s)` for this valid UTF-8 domain | `len(s.encode('utf-8'))` |
| Code points | `utf8.RuneCountInString(s)` | `len(s)` |
| UTF-16 units | `len(utf16.Encode([]rune(s)))` | `len(s.encode('utf-16-le')) // 2` |

Go strings are byte sequences, and [the specification defines their length in
bytes](https://go.dev/ref/spec#String_types). Python [`str` is a sequence of
Unicode code points](https://docs.python.org/3.13/library/stdtypes.html#text-sequence-type-str).
The Go [`unicode/utf8`](https://pkg.go.dev/unicode/utf8#RuneCountInString) and
[`unicode/utf16`](https://pkg.go.dev/unicode/utf16#Encode) library operations give
the other counts. Explicit little-endian Python encoding avoids including a BOM.
Counting UTF-16 here does not imply that a JavaScript runtime was tested.

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
second UTF-16 unit for a four-byte sequence. It does not call either native
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

This executes one native Go batch, one 27-case Gooo batch and a separate Gooo
input-rejection check. Python supplies independently calculated expectations.
The local observation on macOS arm64 (Go 1.27.3, CPython 3.9.6) took about 1.4
seconds: all 27 records agreed, 21 inputs distinguished bytes from code points,
and 8 distinguished code points from UTF-16 units. Runtime and wall time are
recorded per run; this is an observation, not a performance guarantee.

Inspect `evidence/text-length/rows.json` for all inputs and the three observed
records. `execution.stdout` is the original Gooo receipt, `go.stdout` the native
Go output, and `over-limit.stdout` the rejection of a 1025-byte input. Receipt
digests bind the case document and workspace manifest; `summary.json` records
source/log hashes, runtime versions, exit codes and the GitHub execution context
when available. CI retains these artifacts for seven days, including on failure.
Hashes bind content and do not themselves establish author identity.

## What this comparison excludes

The fixed corpus covers empty and NUL strings, CRLF, Korean, accents, combining
sequences, emoji, ZWJ, variation selectors, Unicode encoding boundaries and
strings at 1023/1024 UTF-8 bytes. U+FFFD is tested as an ordinary valid scalar.
Malformed UTF-8 and lone surrogate code points are excluded. Go can store
arbitrary bytes and Python can represent lone surrogates; those broader domains
are not equivalent to this bridge's Text domain.

No normalization is performed: precomposed `é` and `e` + U+0301 stay different
inputs. No field counts grapheme clusters, visual characters or terminal columns.
These 27 observations do not prove correctness over all Unicode strings or
complete Go/Python equivalence. A UI character limit needs a separately specified
unit and may need grapheme segmentation beyond these three counts.

Pinned documentation source revisions and licenses are in
[provenance.json](../bridges/text-length/provenance.json). Code and corpus were
independently authored; executing runtime identities are observed separately.
The [proposal](https://github.com/kimjooyoon/gooo-language-bridge/issues/8) records
the bounded scope. This owned artifact does not count as upstream acceptance.
