# Try HCL optional types in a browser

Open the [base example](https://go.dev/play/p/9ZhU3aBx0H2?v=goprev) or
[proposed-head example](https://go.dev/play/p/Jsv4SQFxD07?v=goprev), then press
**Run**. No local compiler or Gooo installation is needed.

The question is whether rendering an HCL type and parsing it again preserves
optional attributes. A separate example asks whether that also preserves a
value default. The proposed change belongs to sueun-dev in
[HCL #815](https://github.com/hashicorp/hcl/pull/815); this companion is an
independently authored observer, not a duplicate fix or upstream acceptance.

## Read the five results

Both programs contain identical observation code and print JSON lines. Read
`type_equal` for each result:

| Example | Base | Proposed head |
| --- | --- | --- |
| Required Boolean attribute | `true` | `true` |
| Optional Boolean attribute | `false` | `true` |
| Optional attribute inside a list of objects | `false` | `true` |
| Unicode/hyphenated attribute identifiers | `false` | `true` |
| Type of an object with default `42` | `false` | `true` |

The last row is a distinct boundary. On the head, the type is equal, but the
printed constraint contains `optional(number)` without the separate default
`42`. Re-parsing it, applying its defaults to an empty object and converting
to its type produces `{"v":null}`. On the base, the printed type makes `v`
required, so that conversion reports an error. `cty.Type` does not carry the
separate `typeexpr.Defaults` value.

The browser pair covers four type examples and one default boundary. It does
not execute the [96-case native matrix](https://gist.github.com/kimjooyoon/698026d8342ec97b6b668e0171569a14/33132c67b5e7072fe1d3ae6e68ba48a441c6b9c1),
its six intentional quoted-key rejections, or its four default-value probes.
That packet explains why ordinary object keys and type-constraint attribute
identifiers have different acceptance rules.

## Check what actually runs

The links select the Playground's previous stable backend with `?v=goprev`.
On October 22, 2026, both ran Go 1.26.10 on Linux amd64 and matched the local
Go 1.27.3 macOS arm64 stdout exactly. The backend selector is relative and may
advance later. Inspect the actual Go version printed to stderr on each run.

The default Go 1.27.3 backend executed the base, but two head builds timed out
during module downloads. Those failures remain in the evidence packet. The
successful Go 1.26.10 pair does not certify the head on the default backend;
switching backends can change whether a future build completes.

Each program also prints the actual module path, version, checksum and whether
a replacement was used. The pins are development pseudo-versions, not released
v2.24.1:

| Source | Actual source module | Pinned version |
| --- | --- | --- |
| Base | `github.com/hashicorp/hcl/v2` | `v2.24.1-0.20260514123321-9466647a1845` |
| Proposed head | `github.com/sueun-dev/hcl/v2` | `v2.24.1-0.20260711070837-809f3c568d62` |

The head retains canonical imports and explicitly replaces their module with
the author's fork at reviewed commit
`809f3c568d62f0966bdf304837803e602f900d57`. The base commit is
`9466647a1845f1f5c8b8b73b28ea45ff0e6d73e3`. A nominal `require` version alone
does not identify the executed source when a replacement is present; inspect
`source_module`, `source_version`, `source_sum` and `replacement` in stderr.
Go documents this mechanism in its [module replacement guide](https://go.dev/doc/modules/gomod-ref#replace).

## Inspect or reuse the evidence

The [frozen browser packet](https://gist.github.com/kimjooyoon/e3fefafc7748c937bf8bf1f5627c6683/e0da5d311d3ac985c932bc8d243b311367db23ef)
contains both four-file TXTAR programs, original local/hosted results, exact
shared-source readbacks, runtime identities, the failed default-backend
responses, source audit and an offline verifier. Its README explains how to
extract each program and run it locally, and what verification cannot prove.
Before publication, all 370 extracted module files for each source matched
Git blob identities at the corresponding commit. No engine implementation is
copied into this workbench.

The observer and prose are MIT; HCL remains MPL-2.0 under the separate license
in the packet. A source pin or matching sample does not prove general HCL
conformance, performance, upstream CI approval or upstream acceptance. These
examples do not execute Gooo. Return to the [experiment catalog](experiments.md)
to choose another native observation or a Gooo semantic bridge.
