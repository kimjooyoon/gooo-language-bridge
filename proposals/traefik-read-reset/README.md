# Wrapped read-reset criterion: an owned proposal

This packet investigates [Traefik issue 14116](https://github.com/traefik/traefik/issues/14116),
reported by `86wyhdz4hz-sketch`. It contains a **proposed, unsubmitted** two-file
criterion patch and a standalone reproduction. It is not a Traefik build, a
complete upstream regression patch, or an accepted contribution.

## What the reproduction establishes

The pinned `v3.7` source at `7fdde68e1acbfa89cd447ed34bc9c17120e759a7`
uses the first matching `*net.OpError` and requires its operation to be `read`.
[`errors.AsType`](https://pkg.go.dev/errors#AsType) returns the first match.
A copy method can add another `net.OpError`, hiding the actual read operation:

```text
readfrom → read → syscall ECONNRESET
```

The original predicate returns false for that chain. The
[caller](caller-proxy.go.txt) uses true for DEBUG and false for ERROR, but only
when an error exists. Nil means no log, represented as `NO_LOG` in this packet.
Those labels are derived from the caller's branch; the harness does not execute
`ServeTCP` or capture zerolog output.

The proposal skips `readfrom`/`writeto` operation contexts and checks the underlying
operation. A write reset, an ambiguous copy reset without a read operation, or a
read failure with another cause still takes the ERROR branch. Original source
and its MIT notice are preserved in [original/](original/) and
[LICENSE.traefik](LICENSE.traefik); file/blob hashes are in
[provenance.json](provenance.json).

## Reproduce with native Go and Gooo

From the repository root with the documented pinned compiler installed:

```sh
python3 tools/verify_read_reset.py --gooo .bin/gooo
```

The verifier compiles the original predicate files unchanged in a small
standard-library-only module. It injects the same owned fixtures before and
after applying [proposal.patch](proposal.patch). It requires five original
classification failures, all sixteen proposed/race passes, and the same sixteen
Gooo results. No Traefik cloud/provider dependencies or Docker images are needed
for this bounded test.

One case creates real loopback TCP pairs, sends a peer reset with `SetLinger(0)`,
and forces `io.Copy` through `TCPConn.ReadFrom` by hiding the source's `WriterTo`.
It requires the actual error to have the reported `readfrom → read` shape and
reset cause. Read/write deadlines bound the copy. Other cases cover direct and
formatted errors, both copy wrappers, writes, non-reset reads, nil and plain errors.

The [Gooo activity](../../bridges/read-reset/main.gooo) gives the observed facts
and decision stable IDs. Native Go supplies ordered operation labels, whether an
error exists and whether its cause is a reset; Gooo interprets those facts into
`DEBUG`, `ERROR` or `NO_LOG`. It does not parse an error message or call the proposed
predicate. Source/manifest/case digests and every actual delivery are checked.

Inspect `evidence/read-reset/rows.json`, original native JSON test events and the
Gooo execution receipt. The local macOS arm64 Go 1.27.3 run completed in about
6.8 seconds. CI repeats it on Linux in the existing bounded job. Windows code is
cross-compiled only; Windows runtime behavior is not certified.

## Submission boundary

The pinned [Traefik AGENTS.md](https://github.com/traefik/traefik/blob/7fdde68e1acbfa89cd447ed34bc9c17120e759a7/AGENTS.md)
says **“Keep issue and PR conversations human.”** It also says an agent-drafted
message should be rewritten in the contributor's own voice before sending.
This packet therefore does not post upstream comments, triage messages or a PR.
The original policy text is retained in [upstream-AGENTS.txt](upstream-AGENTS.txt).

The [submission guide](https://github.com/traefik/traefik/blob/7fdde68e1acbfa89cd447ed34bc9c17120e759a7/docs/content/contributing/submitting-pull-requests.md)
requires project validation and integration checks. Full Traefik `make validate`,
generation, conformance and integration tests have not been run. The standalone
test harness would still need to be adapted to Traefik's normal test conventions
and validated in that repository before submission. Passing this packet's CI
does not waive those requirements.

The model is finite: linear, acyclic chains with at most three `net.OpError`
nodes. Branched/joined errors, cyclic errors, arbitrary-depth equivalence, the
reported Go 1.25.11 environment and the Teleport/browser deployment are outside
this verification. The proposed native loop is broader than that finite Gooo
model, so no general equivalence claim is made. Socket lifecycle and forwarding
behavior are unchanged by the proposed predicate diff, but have not been exercised
through Traefik itself. Implementation and investigation were assisted by Codex.
