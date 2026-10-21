# Moving Python integer division to Go: keep the rounding rule explicit

A mechanical translation can change a result even when both programs use
integers. Python's `-7 // 3` is `-3`; Go's `int64(-7) / int64(3)` is `-2`.
This matters when a quotient determines a bucket, index or boundary.

[Python defines `//` using floor division](https://docs.python.org/3/reference/expressions.html#binary-arithmetic-operations).
[Go integer division truncates toward zero](https://go.dev/ref/spec#Integer_operators).
This repository compares the actual runtimes and makes the intended translation
an explicit Gooo activity. These are language semantics, not bugs in either runtime.

## Five revealing inputs

| Dividend | Divisor | Native Go quotient | Python floor quotient | Gooo floor adapter |
| ---: | ---: | ---: | ---: | ---: |
| 7 | 3 | 2 | 2 | 2 |
| -7 | 3 | -2 | -3 | -3 |
| 7 | -3 | -2 | -3 | -3 |
| -7 | -3 | 2 | 2 | 2 |
| -6 | 3 | -2 | -2 | -2 |

Negative operands alone do not imply a correction: exact division already agrees.
If the quotient has a nonzero remainder and the operands have opposite signs,
subtract one from the truncating quotient to obtain the floor quotient.

The [Gooo source](../bridges/python-floor/main.gooo) expresses that rule:

```gooo
activity FloorDivide(Integer, Integer) -> Integer
  id "urn:gooo:bridge:python:floor-divide" computes `let quotient=input0/input1
let remainder=input0-quotient*input1
if remainder != 0 {
if input0 < 0 {if input1 > 0 {quotient=quotient-1}}
if input0 > 0 {if input1 < 0 {quotient=quotient-1}}
}
return quotient`
```

The linked file also declares its package, namespace and Integer identity. The
stable activity ID names the behavior being checked. An ID does not establish
correctness: independent runtime observations supply the evidence. The adapter
implements a familiar rounding rule; Gooo's contribution here is keeping that
intent and its identity alongside the program and its recorded observations.

## Reproduce all 120 pairs

From a checkout of this repository, with Python 3.9+ and Go 1.27.3:

```sh
mkdir -p .bin
GOBIN="$PWD/.bin" GOTOOLCHAIN=go1.27.3 go install github.com/kimjooyoon/meta-ontology-go/cmd/gooo@v0.6.38-dev
python3 tools/compare_division.py --gooo .bin/gooo
```

The runner invokes Gooo once for a fresh verification and invokes the independent
[native Go reference](../examples/division-reference/main.go) once for all inputs.
Python calculates each expected floor quotient with its own `//` operator.
It records **30 Go/Python differences out of 120 pairs**, with **120 Gooo/Python
matches**. This percentage describes the chosen enumeration, not typical programs.

The domain is dividends -7 through 7, and divisors -4 through 4 excluding zero.
It includes positive and negative dividends/divisors, exact and inexact division,
and zero dividends. It excludes zero divisors, floats, arbitrary-precision
compatibility, overflow and minimum-machine-integer divided by -1.
Do not generalize this result to all Python integer behavior.

## Inspect the evidence

- `evidence/division-comparison/rows.json`: each input and its three observed results.
- `evidence/division-comparison/summary.json`: counts, source/receipt hashes and native Go identity.
- `evidence/execution.json`: the original Gooo receipt, including the activity ID,
  positional inputs, actual outputs, case indices and compiler/runtime information.
- `evidence/compiler.json`: Gooo build identity; the companion bridge summary records Python identity.

The comparison joins observations by input pair and recorded case identity.
It rejects missing or duplicate rows, a different activity/input binding,
Boolean values impersonating integers and a native result that violates Go's
quotient/remainder invariants. A top-level PASS count cannot replace those checks.
The tests deliberately corrupt those observations to exercise the boundary.

CI preserves the original files for seven days. After artifact expiry, replay
the source revision to obtain new observations rather than treating an expired
artifact link as evidence. No model call, paid service or cloud account is needed.
