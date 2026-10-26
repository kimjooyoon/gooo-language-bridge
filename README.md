# Pointer float comparisons in Expr PR #983

This independently authored observer examines the float32 literal comparison fix requested in [issue #609](https://github.com/expr-lang/expr/issues/609#issuecomment-2131289092) and implemented by [PR #983](https://github.com/expr-lang/expr/pull/983).

- Base: `4b31df3a2e0eefec04c017a82a00e0f08541d3e4`
- Proposed head: `75aa119320b57957cdc4de2fc8669e239e6c18c4`

With a float32 value of 12.34, the head fixes comparison of a plain float32 field with a floating literal. A pointer field still compares false in either operand order, while adding unary `+` makes the same comparison true. Double pointers and a negative pointer value show the same remaining gap. Exactly representable 1.5, pointer-to-float64 and integer-pointer controls remain true. Mixed float32/float64 comparison remains false.

The pointer mismatch was already present on the base. This identifies an incomplete fix, not a newly introduced pointer regression. The source already dereferences operands in checker `binaryNode` and compiler `equalBinaryNode`; the new literal patcher checks the original operand type instead.

## Reproduce

Check out either exact revision above, keep `observer.go` outside that checkout, and run from the checkout:

```sh
GOTOOLCHAIN=local GOWORK=off GOENV=off GOPROXY=off \
  GOMAXPROCS=2 GOMEMLIMIT=128MiB \
  go run -mod=readonly -p=2 /path/to/observer.go
```

The same source evaluates 13 finite expressions under both optimization settings. All 26 observations per revision compiled and ran without errors; the boolean differences are recorded, not hidden behind a process exit code. Both unmodified revisions ran with already-installed Go 1.27.3 on darwin/arm64, with no dependency or SDK downloads. The recording supervisor imposed a 60-second deadline on each process and verified its process group was absent afterward. Both exited normally, totaling about 2.626 seconds including compilation. GOMEMLIMIT is a soft runtime target, not a hard cap.

`base/` and `head/` contain original output streams. `capture.json` is a portable projection of the original process records with local paths omitted. `validation.json` records the finite comparison checks; `manifest.json` binds the other files by byte count and SHA-256. No patched alternative, full suite, race test, benchmark, upstream acceptance or Gooo compatibility was evaluated. AI assistance was used.
