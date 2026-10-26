# Caddy #8205: requested sidecar-header review

The existing author was asked to keep precompressed sidecar headers off `If-Match`
precondition failures. This packet supplies an optional patch and regression tests
for that request, against `ab11ecd6aba5508fa82ac6fff5789d938cffa02c`.

[Maintainer request](https://github.com/caddyserver/caddy/pull/8205#discussion_r4255482391).

`production.patch` stages the sidecar headers until `ServeContent` commits its
original status, before the status override is applied. Only original 200/206
responses receive the encoding; 206 keeps the standard library's calculated
single-range or multipart length. Conditional 304 and 412 responses do not get
sidecar headers, including when their status is overridden to 200.

`precompressed_review_test.go` adds conditional, override, HEAD, ignored-Range,
unsatisfiable-Range and multipart controls. The existing full-response,
single-range and earlier handler-error tests remain in place. An ignored Range
also exposes a missing Content-Length in the handler’s committed recorder
headers on the original revision; the patch uses the actual 200 status to supply
it. This does not establish the header on every real network response, since
net/http can infer a length for small responses.

## Reproduce

Use the exact Caddy revision above, copy `precompressed_review_test.go` into
`modules/caddyhttp/fileserver/`, run the focused precompressed tests, then apply
`production.patch` and run the fileserver package with `-short` (no race flag). `run.py` automates this in a
fresh temporary checkout with pinned Go 1.27.3, a total time budget and bounded
logs. It downloads Caddy dependencies only in the disposable hosted runner.

The branch-specific workflow uses one standard Linux job with a 12-minute limit.
It does not upload caches or artifacts; raw command logs are retained in the job
log. Execution results will be recorded after the job finishes.

This is AI-generated review support prepared by OpenAI Codex (GPT-6), not an
upstream pull request or a claim of maintainer acceptance, operator code review,
CLA certification, complete Caddy CI, or a release. Caddy-derived code and this
patch/test are provided under the accompanying Apache-2.0 license. The original
PR author retains ownership of the implementation and its final validation.
