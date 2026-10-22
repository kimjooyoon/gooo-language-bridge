# An unfinished flag is useful input during completion

A parser sees the same unfinished `-ab` token in two different requests:
run the command, or help finish typing it. For boolean `a` and string `b`, the
first request needs a missing-value error. The second needs to deliver `-ab`
to the completion callback so that the callback can use the current input.

That context is part of the meaning of the request. Retaining an unfinished
token during completion does not make it a valid execution argument.

## Observe the boundary in urfave/cli

[PR #2485](https://github.com/urfave/cli/pull/2485) adds the same tail preservation
that the parser already uses for single flags to grouped short flags.
With `UseShortOptionHandling` enabled and a `ShellComplete` callback that reads
`cmd.Args().Slice()`, these observations hold at the root, child and nested command:

| Invocation tail | Request | Original callback/action outcome | Patched outcome |
| --- | --- | --- | --- |
| `value -ab` | Complete | callback gets `["value"]` | callback gets `["value", "-ab"]` |
| `value -a한` | Complete | callback gets `["value"]` | callback gets `["value", "-a한"]` |
| `value -az` | Complete | callback gets `["value"]` | callback gets `["value", "-az"]` |
| `value -b` | Complete | callback gets `["value", "-b"]` | same |
| `value -ab` | Execute | error; action stays uncalled | same |
| `value -ab=given` | Execute | action runs | same |
| `value -ab=` | Complete | callback gets `["value"]`; group consumed | same |

The commands declare boolean `a` and string flags `b` and `한`; `z` is unknown.
Completion requests end with `--generate-shell-completion`. The fixture invokes
`Command.Run` directly and observes callback arguments, errors and whether the
action or completion callback ran. Shell scripts and terminal interaction are
outside this check.

## Give the request context a stable identity

The [Gooo Request](../bridges/completion-intent/main.gooo) assigns separate IDs
to the token, completion mode and incompleteness classification. The independent
corpus declares incompleteness before either implementation executes. For example,
`-ab` alone is incomplete, while `-ab given` is complete because its following
argument supplies the value; both share the same token text.

```gooo
activity Resolve(Request) -> Text id "urn:gooo:cli:resolve-input-intent" computes `
if input.incomplete {
    if input.completion {return "PENDING:" + input.token}
    return "REJECT"
}
return "CONSUMED"
`

This activity resolves an explicit intent policy from supplied facts. It does
not tokenize arguments or determine whether an arbitrary flag group is valid.
The independent native observer measures the actual parser/callback behavior.
Its `REJECT` label denotes a CLI error; Gooo successfully calculating that label
is a passing semantic observation, not a compiler failure.

## Reproduce

With Python 3.9+, Go 1.27.3 and the pinned compiler from the [README](../README.md):

```sh
python3 tools/verify_cli_completion.py --gooo .bin/gooo
```

The verifier fetches exact original and submitted source revisions into a
temporary checkout, retains their parser source, module files and MIT license,
and injects the same independently authored [observer](../tests/fixtures/cli_completion_witness_test.go).
It requires nine original mismatches, 20 patched matches and 20 race-checked
matches. It then executes the Gooo activity against the native input records
and requires all 20 results, exact delivery identities and original input digests.

These are 20 native cases and 12 distinct Gooo policy inputs: command depth is
varied in the native commands and is not a Gooo input. Eleven controls remain
unchanged. Coverage includes a single-flag partial input, ordinary errors,
separate/equals values and explicit empty values.

Inspect `evidence/completion-intent/rows.json` for the original, patched and Gooo
results; `before.stdout`, `after.stdout` and `race.stdout` retain original Go
JSON test events and witness records. `execution.stdout` retains the original
Gooo receipt. `summary.json` binds source/log hashes, observed runtime/compiler
identity and GitHub execution context when present. The verifier recomputes native
outcomes from the callback/error records and rejects missing cases, duplicate
witnesses, changed arguments or contradictory declared results.

The existing single 12-minute CI job retains artifacts for seven days. No model,
new service or additional runner job is used. Hashes bind content; they do not
prove authorship or upstream acceptance. Source revisions and exclusions are in
[provenance.json](../bridges/completion-intent/provenance.json).

This finite comparison covers the listed command graph and input cases. It does
not certify the full CLI grammar, arbitrary flags or shell integration, flag
mutation behavior, error message equality or all future parser revisions.
The upstream submission has passing CI; review and acceptance remain upstream's.
