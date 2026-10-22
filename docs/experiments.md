# Choose a reproducible language experiment

Start with a concrete question, then use the smallest useful reproducer below.
Browser examples need no local installation. Native experiments do not require
a Gooo compiler; semantic bridges additionally execute an independently authored
Gooo activity with stable field and operation identities.

These are bounded observations recorded on October 22, 2026, not a live upstream
acceptance dashboard. Pinned packets preserve the tested source and scope.
Several observe unmerged PRs; the linked upstream PR remains authoritative for
current status and the original author's work. A matching result is not general
language equivalence, and a difference is not automatically a new bug.

## Run in a browser

| Question | Start here | What to inspect |
| --- | --- | --- |
| How can an embedded script keep defaults while accepting host inputs? | [Tengo defaults and overrides](https://go.dev/play/p/ZTWz3dxvg5V) | Five runs of one compiled program: empty, full, zero-valued, partial and empty inputs. The input map still needs registration; it does not discover unknown globals. [Submitted documentation](https://github.com/d5/tengo/pull/496). |
| Can two Go types have the same display label? | [pflag native type-identity counterexample](https://go.dev/play/p/GsveDskxbgt) | Four source/target pairs on a pinned original pflag revision. The proposed fix is separate from this baseline demonstration. [Submitted fix](https://github.com/spf13/pflag/pull/529). |

Both programs report their actual runtime/dependency identity. Their
module versions are pinned development pseudo-versions, not claims of a newer
published release. Inspect those pins before adapting either example.

## Native observations: no Gooo compiler needed

For a short first run, use [three Goja/Node.js observations](first-observation.md).
Then choose a question from the following index. Frozen packets include their
own README, source identities, original observations and verification steps;
read those instructions before running code.

| Question | Reproduction or frozen evidence | Evidence boundary |
| --- | --- | --- |
| How does an unmerged JavaScript engine change affect my script? | [Goja/Sobek snapshot driver](../examples/js-differential/README.md) | Compare a trusted script in an exact engine commit and Node.js, optionally against a base. Retain introduced, corrected and unchanged differences. The guide includes another author's Sobek JSON.parse fix. |
| Does a JSON optimization preserve object mutation and serialization behavior? | [Goja JSON experiment](https://gist.github.com/kimjooyoon/caeb5eecd1634b7173cfc3468a328659/075b915af71407833d283ce62b13f0893b423271) | 187 cases: five corrected base/reference differences, three known raw UTF-16 differences retained, none introduced in this corpus. Node 22 and 24 are both V8. No performance claim. |
| What happens when Unicode normalization sees lone UTF-16 surrogates? | [Goja normalization experiment](https://gist.github.com/kimjooyoon/cdc0106aefec97d80b8fbd75ac6ff5aa/5d39c4a5e3871541a0372e9b57424ed32444628e) | 24 cases include twelve known differences and twelve controls. Code-unit observations precede Go string export. This is an existing report, not a fresh bug to resubmit. |
| How should integers compare with binary64 values near precision boundaries? | [CEL numeric comparison experiment](https://gist.github.com/kimjooyoon/e5503fc39f13d1cf6f5401fe11b4ee04/d1726d80d180ec8573bf01854531f2a0fb231797) | 3,992 pairs, exact Python Fraction and Node BigInt references; seventeen mismatching base pairs become zero at the tested PR head. Includes NaN's unordered cases. |
| Does a cost-model version pin preserve earlier estimates? | [CEL prefix/suffix cost experiment](https://gist.github.com/kimjooyoon/55d0e9366f975ef4799f7c4c00fc89a0/c6d9f5cdd55633d50ecc74df8fee6912f599842c) | 112 inputs, exact/upper hints and three model versions. Static estimate changes under version 0 are a compatibility question; runtime charges are explicitly unversioned. |
| Does a Starlark regexp wrapper expose the intended replacement behavior? | [Starlark regexp adapter experiment](https://gist.github.com/kimjooyoon/75ae5732302fc4b075186659c7c1eb48/111e4658481ddc1fc2cdbf5cd817c5e93df281fc) | 240 pattern/subject pairs and 1,680 string replacements. Compares the adapter with the same underlying Go regexp implementation; literal/template distinctions are design observations, not confirmed bugs. |
| Where do Lua and Python floor-division models agree or diverge? | [Native GoLua observer](../examples/lua-division-reference/README.md) | Execute the pinned runtime's Lua `//` chunk without a Gooo compiler or separate Lua executable. Small inputs agree; int64 wrapping and zero division are preserved separately. |

The JavaScript driver returns exit 1 for a valid `DIFFERENCES` report. It is not
a provider failure or an approval. The JSON and normalization examples deliberately
retain differences; do not delete those rows merely to obtain a zero exit code.

## Execute a Gooo semantic bridge

These commands run the actual Gooo activity and compare original runtime
observations. Follow the [compiler/runtime setup](../README.md#reproduce-the-semantic-comparisons)
first. Each guide describes its input units, stable identities and exclusions.

| Behavior | Guide | Reproduction command |
| --- | --- | --- |
| Integer floor division | [Go, Python and pinned GoLua](python-go-integer-division.md): 120 bounded inputs; three additional Lua boundaries remain outside Gooo | `python3 tools/compare_division.py --gooo .bin/gooo` |
| String length units | [UTF-8 bytes, code points and UTF-16 units](string-length-units.md): 27 scalar strings; not grapheme or display width | `python3 tools/compare_text_length.py --gooo .bin/gooo` |
| Incomplete flag groups | [Execution versus completion intent](completion-input-intent.md): 20 native cases, 12 distinct policy inputs; token classification is supplied | `python3 tools/verify_cli_completion.py --gooo .bin/gooo` |
| Forward Delete | [One press, one edit](delete-forward-newline.md): eight native/Gooo cases; rune and byte cursor units are explicit | `python3 tools/verify_bubbles_delete.py --gooo .bin/gooo` |
| Wrapped TCP read resets | [Owned Traefik criterion study](../proposals/traefik-read-reset/README.md): sixteen finite decisions; unsubmitted upstream | `python3 tools/verify_read_reset.py --gooo .bin/gooo` |

## Verify and contribute

For a downloaded complete CI bundle, use the [offline integrity audit](audit-ci-evidence.md).
It checks hashes, source objects and the supplied execution tuple without
re-executing the languages. Its guide explains the separate GitHub run and
artifact identity checks. Passing this audit alone does not certify semantics.

Before starting upstream work, [inspect recent merges and existing attempts](contribution-candidate-check.md)
and read the upstream participation rules. Keep proposed, submitted and accepted
work distinct. The [current contribution record](https://github.com/kimjooyoon/gooo-language-bridge/issues/24)
links dated evidence; the [older submission notes](contributions.md) retain their
original scope. Neither replaces the current upstream status.

To add a useful counterexample or a new bounded activity, choose a
[contribution path](../CONTRIBUTING.md). A small native observation is a valid
starting point; a `.gooo` file is required only when implementing a semantic
bridge. Credit existing reports and patches when reusing their evidence.
