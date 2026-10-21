# One Delete press should perform one edit

In [Bubbles](https://github.com/charmbracelet/bubbles), a textarea Delete press
on the final character of a non-final line removed the character **and** its
following newline. Put the cursor on `b` in `ab\ncd`: the original returned `acd`,
while the intended result is `a\ncd`. A second Delete at that now-existing line
end should join the lines. These are two edits, requiring two keypresses.

[Submitted PR #1072](https://github.com/charmbracelet/bubbles/pull/1072) moves the
line-end check before deletion. It adds no Gooo dependency to Bubbles. The
[original report](https://github.com/charmbracelet/bubbles/issues/1071) contains
a standalone public-API reproducer that needs no terminal.

## Express the edit independently in Gooo

The [source activity](../bridges/forward-delete/main.gooo) gives the operation the
stable ID `urn:gooo:editing:delete-forward-scalar`. Its input has separate stable
identities for the text and `byte_column`. It removes the UTF-8 scalar at that
boundary; a newline is removed when the cursor is already on the newline.
At the end of the complete text, the result is unchanged.

Bubbles positions its cursor in runes. The native observation fixture records
that position and the corresponding byte offset **before** the edit. It then
calls the actual Bubbles `Update` with `tea.KeyDelete` and records `Value()`.
Gooo receives the original text and byte offset, not a precomputed output.
It uses its own bounded byte scan and slicing. No input construction or model
search participates in the comparison.

| Original text | Rune column, first line | Expected after Delete | Original Bubbles |
| --- | ---: | --- | --- |
| `ab\ncd` | 1 | `a\ncd` | `acd` |
| `a\nb` | 0 | `\nb` | `b` |
| `a界\n다` | 1 | `a\n다` | `a다` |
| `abc\ncd` | 1 | `ac\ncd` | unchanged behavior |
| `ab\ncd` | 2 | `abcd` | unchanged behavior |
| `\ncd` | 0 | `cd` | unchanged behavior |
| `ab` | 1 | `a` | unchanged behavior |
| `ab` | 2 | `ab` | unchanged behavior |

Here `\n` represents an actual LF. This is an eight-input comparison, not a
proof for arbitrary editing. It covers first-line, valid UTF-8 scalar boundaries
with no selection. Grapheme clusters, CRLF handling, cursor movement after the
edit, visual width, terminal rendering and other keybindings are outside this
comparison. The Gooo activity's declared preconditions are not an input validator.

## Reproduce the source-bound observations

Use the pinned Gooo compiler setup in the [README](../README.md), then run:

```sh
python3 tools/verify_bubbles_delete.py --gooo .bin/gooo
```

The command fetches the original and submitted commit into one temporary
checkout, injects the same [observation fixture](../tests/fixtures/bubbles_delete_witness_test.go)
on both, and requires exactly three original failures followed by eight patched
passes and eight race-checked passes. The fresh Gooo execution must match all
eight native expected values, with the exact activity ID, typed inputs and
case/manifest digests. Inputs and expectations must agree across native runs.

`evidence/forward-delete/` retains original Go test events, native source files,
module files, their MIT license, compiler/runtime identity, cases, Gooo receipt
and source/log hashes. The existing single bounded CI job runs this verifier
without credentials, a TTY, model calls or a paid service. Each command has a
timeout; there is no polling loop or new runner matrix.

The [provenance](../bridges/forward-delete/provenance.json) pins the source
revisions. This focused independent CI does not certify the complete Bubbles
suite, upstream CI approval, Windows runtime behavior or upstream acceptance.
The submitted patch's broader **local** checks are described separately in its PR.
