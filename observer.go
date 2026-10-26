package main

import (
	"encoding/json"
	"os"
	"runtime"

	"github.com/expr-lang/expr"
)

type observation struct {
	Expression   string `json:"expression"`
	Optimized    bool   `json:"optimized"`
	Value        any    `json:"value"`
	CompileError string `json:"compile_error,omitempty"`
	RunError     string `json:"run_error,omitempty"`
}

func main() {
	f := float32(12.34)
	p := &f
	n := float32(-12.34)
	exact := float32(1.5)
	d := float64(12.34)
	i := 3
	env := struct {
		V        float32
		P        *float32
		PP       **float32
		Negative *float32
		Exact    *float32
		D        *float64
		I        *int
	}{f, p, &p, &n, &exact, &d, &i}
	expressions := []string{
		"V == 12.34", "12.34 == V",
		"P == 12.34", "12.34 == P", "+P == 12.34",
		"PP == 12.34", "+PP == 12.34",
		"Negative == -12.34", "P == V",
		"Exact == 1.5", "D == 12.34", "I == 3", "V == D",
	}
	rows := []observation{}
	for _, optimized := range []bool{true, false} {
		for _, source := range expressions {
			row := observation{Expression: source, Optimized: optimized}
			program, err := expr.Compile(source, expr.Env(env), expr.Optimize(optimized))
			if err != nil {
				row.CompileError = err.Error()
			} else {
				row.Value, err = expr.Run(program, env)
				if err != nil {
					row.RunError = err.Error()
				}
			}
			rows = append(rows, row)
		}
	}
	result := struct {
		GoVersion    string        `json:"go_version"`
		OS           string        `json:"os"`
		Arch         string        `json:"arch"`
		Observations []observation `json:"observations"`
	}{runtime.Version(), runtime.GOOS, runtime.GOARCH, rows}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(result); err != nil {
		panic(err)
	}
}
