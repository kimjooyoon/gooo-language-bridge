package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"runtime"

	"github.com/itchyny/gojq"
)

type event struct {
	Kind           string `json:"kind"`
	Value          any    `json:"value"`
	Error          string `json:"error,omitempty"`
	ErrorType      string `json:"error_type,omitempty"`
	Halt           bool   `json:"halt,omitempty"`
	HaltValue      any    `json:"halt_value,omitempty"`
	HaltValueIsNil bool   `json:"halt_value_is_nil,omitempty"`
	Canceled       bool   `json:"canceled,omitempty"`
}

func describe(v any) event {
	if err, ok := v.(error); ok {
		e := event{Kind: "error", Error: err.Error(), ErrorType: fmt.Sprintf("%T", err), Canceled: errors.Is(err, context.Canceled)}
		var halt *gojq.HaltError
		if errors.As(err, &halt) {
			e.Halt = true
			e.HaltValue = halt.Value()
			e.HaltValueIsNil = halt.Value() == nil
		}
		return e
	}
	return event{Kind: "value", Value: v}
}

func collect(it gojq.Iter) []event {
	out := []event{}
	for i := 0; i < 20; i++ {
		v, ok := it.Next()
		if !ok {
			return out
		}
		out = append(out, describe(v))
	}
	panic("unexpectedly exceeded 20 Next calls")
}

func compile(s string, opts ...gojq.CompilerOption) *gojq.Code {
	q, err := gojq.Parse(s)
	if err != nil {
		panic(err)
	}
	c, err := gojq.Compile(q, opts...)
	if err != nil {
		panic(err)
	}
	return c
}

type countedInput struct {
	Values []any
	Calls  int
}

func (c *countedInput) Next() (any, bool) {
	c.Calls++
	if len(c.Values) == 0 {
		return nil, false
	}
	v := c.Values[0]
	c.Values = c.Values[1:]
	return v, true
}

func main() {
	mixed := `1, error("first"), null, error("second"), 2`
	code := compile(`1, 2`)
	it := code.Run(nil)
	first := collect(it)
	sameAgain := collect(it)
	fresh := collect(code.Run(nil))
	input := &countedInput{Values: []any{10, 20, 30}}
	inputCode := compile(`inputs`, gojq.WithInputIter(input))
	inputRun := inputCode.Run(nil)
	v, ok := inputRun.Next()
	if !ok {
		panic("missing first input")
	}
	afterOne := input.Calls
	remainder := collect(inputCode.Run(nil))
	afterSecond := input.Calls
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	result := map[string]any{
		"source":                      "56ae40d64ce0f4824803e789704e1a1a49293642",
		"runtime":                     map[string]string{"go": runtime.Version(), "os": runtime.GOOS, "arch": runtime.GOARCH},
		"scope":                       "Existing public Iter API only; RunSeq/RunSeqWithContext are not implemented or executed here.",
		"mixed":                       map[string]any{"query": mixed, "events": collect(compile(mixed).Run(nil))},
		"empty":                       collect(compile(`empty`).Run(nil)),
		"halt_continued_deliberately": collect(compile(`1, halt, 2`).Run(nil)),
		"missing_variable":            collect(compile(`$x`, gojq.WithVariables([]string{"$x"})).Run(nil)),
		"precanceled_context":         collect(compile(`1, 2`).RunWithContext(ctx, nil)),
		"reuse":                       map[string]any{"first": first, "same_iterator_again": sameAgain, "new_Run": fresh},
		"stateful_input":              map[string]any{"first_event": describe(v), "input_Next_calls_after_one_result": afterOne, "new_Run_events": remainder, "input_Next_calls_after_new_Run": afterSecond},
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(result); err != nil {
		panic(err)
	}
}
