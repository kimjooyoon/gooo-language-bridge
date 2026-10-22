// Independent bounded HCL public-API observer. SPDX-License-Identifier: MIT
package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"os"
	"runtime"
	"runtime/debug"

	"github.com/hashicorp/hcl/v2"
	"github.com/hashicorp/hcl/v2/ext/typeexpr"
	"github.com/hashicorp/hcl/v2/hclsyntax"
	"github.com/zclconf/go-cty/cty"
	"github.com/zclconf/go-cty/cty/convert"
	ctyjson "github.com/zclconf/go-cty/cty/json"
)

var constraints = map[string]string{"required": "object({v=number})", "optional": "object({v=optional(number)})", "default-zero": "object({v=optional(number,0)})", "default-42": "object({v=optional(number,42)})"}

type input struct {
	ID          string `json:"id"`
	Declaration string `json:"declaration"`
	State       string `json:"state"`
	Value       *int64 `json:"value"`
}
type resolution struct {
	Accepted bool  `json:"accepted"`
	IsNull   bool  `json:"is_null"`
	Value    int64 `json:"value"`
}
type row struct {
	ID            string          `json:"id"`
	Declaration   string          `json:"declaration"`
	State         string          `json:"state"`
	Value         int64           `json:"value"`
	Constraint    string          `json:"constraint"`
	Input         json.RawMessage `json:"input"`
	AfterDefaults json.RawMessage `json:"after_defaults"`
	Result        json.RawMessage `json:"result"`
	Diagnostic    string          `json:"diagnostic"`
	Actual        resolution      `json:"actual"`
}

func raw(v cty.Value) json.RawMessage {
	b, e := ctyjson.Marshal(v, v.Type())
	if e != nil {
		panic(e)
	}
	return b
}
func observe(in input) row {
	source := constraints[in.Declaration]
	expr, d := hclsyntax.ParseExpression([]byte(source), "declaration.hcl", hcl.InitialPos)
	if d.HasErrors() {
		panic(d.Error())
	}
	ty, defaults, d := typeexpr.TypeConstraintWithDefaults(expr)
	if d.HasErrors() {
		panic(d.Error())
	}
	values := map[string]cty.Value{}
	if in.State == "null" {
		values["v"] = cty.NullVal(cty.Number)
	} else if in.State == "number" {
		values["v"] = cty.NumberIntVal(*in.Value)
	}
	original := cty.ObjectVal(values)
	applied := original
	if defaults != nil {
		applied = defaults.Apply(original)
	}
	r := row{ID: in.ID, Declaration: in.Declaration, State: in.State, Value: *in.Value, Constraint: source, Input: raw(original), AfterDefaults: raw(applied)}
	converted, e := convert.Convert(applied, ty)
	if e != nil {
		r.Diagnostic = e.Error()
		return r
	}
	r.Result = raw(converted)
	v := converted.GetAttr("v")
	r.Actual.Accepted = true
	r.Actual.IsNull = v.IsNull()
	if !v.IsNull() {
		n, accuracy := v.AsBigFloat().Int64()
		if accuracy != big.Exact {
			panic("non-int64 observation")
		}
		r.Actual.Value = n
	}
	return r
}
func identity() error {
	info, ok := debug.ReadBuildInfo()
	if !ok {
		return errors.New("missing build identity")
	}
	for _, dep := range info.Deps {
		if dep.Path == "github.com/hashicorp/hcl/v2" {
			if dep.Replace != nil {
				return errors.New("unexpected HCL replacement")
			}
			return json.NewEncoder(os.Stdout).Encode(map[string]any{"go": runtime.Version(), "os": runtime.GOOS, "arch": runtime.GOARCH, "module": dep.Path, "version": dep.Version, "sum": dep.Sum, "constraints": constraints})
		}
	}
	return errors.New("missing HCL module")
}
func run() error {
	if len(os.Args) == 2 && os.Args[1] == "--identity" {
		return identity()
	}
	var reader io.Reader = os.Stdin
	if len(os.Args) == 3 && os.Args[1] == "--input" {
		f, e := os.Open(os.Args[2])
		if e != nil {
			return e
		}
		defer f.Close()
		reader = f
	} else if len(os.Args) != 1 {
		return errors.New("expected --input FILE or stdin")
	}
	limited := &io.LimitedReader{R: reader, N: 65537}
	data, e := io.ReadAll(limited)
	if e != nil {
		return e
	}
	if len(data) > 65536 {
		return errors.New("input byte limit")
	}
	var inputs []input
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if e = decoder.Decode(&inputs); e != nil {
		return e
	}
	if decoder.Decode(new(any)) != io.EOF {
		return errors.New("extra JSON data")
	}
	if len(inputs) == 0 || len(inputs) > 64 {
		return errors.New("expected 1..64 cases")
	}
	seen := map[string]bool{}
	for _, in := range inputs {
		if len(in.ID) == 0 || len(in.ID) > 64 || seen[in.ID] {
			return errors.New("duplicate/invalid case identity")
		}
		seen[in.ID] = true
		if _, ok := constraints[in.Declaration]; !ok {
			return errors.New("unknown declaration")
		}
		if in.State != "missing" && in.State != "null" && in.State != "number" {
			return errors.New("unknown input state")
		}
		if in.Value == nil {
			return errors.New("missing numeric payload")
		}
		if in.State != "number" && *in.Value != 0 {
			return errors.New("noncanonical unused value")
		}
	}
	rows := make([]row, 0, len(inputs))
	for _, in := range inputs {
		rows = append(rows, observe(in))
	}
	return json.NewEncoder(os.Stdout).Encode(rows)
}
func main() {
	if e := run(); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(2)
	}
}
