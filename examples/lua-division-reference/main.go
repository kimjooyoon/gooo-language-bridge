package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"runtime"
	"runtime/debug"

	rt "github.com/arnodel/golua/runtime"
)

const source = "local a, b = ...; return a // b"

type input struct {
	A *int64 `json:"a"`
	B *int64 `json:"b"`
}
type observation struct {
	A        int64  `json:"a"`
	B        int64  `json:"b"`
	Quotient *int64 `json:"quotient,omitempty"`
	Error    string `json:"error,omitempty"`
}

func run() error {
	if len(os.Args) == 2 && os.Args[1] == "--identity" {
		identity := map[string]string{"go": runtime.Version(), "os": runtime.GOOS, "arch": runtime.GOARCH, "lua_source": source}
		if info, ok := debug.ReadBuildInfo(); ok {
			for _, d := range info.Deps {
				if d.Path == "github.com/arnodel/golua" {
					if d.Replace != nil {
						return fmt.Errorf("unexpected GoLua module replacement")
					}
					identity["module"], identity["version"], identity["sum"] = d.Path, d.Version, d.Sum
				}
			}
		}
		return json.NewEncoder(os.Stdout).Encode(identity)
	}
	var stream io.Reader = os.Stdin
	if len(os.Args) == 3 && os.Args[1] == "--input" {
		file, err := os.Open(os.Args[2])
		if err != nil {
			return err
		}
		defer file.Close()
		stream = file
	} else if len(os.Args) != 1 {
		return fmt.Errorf("expected --input FILE, --identity or standard input")
	}
	raw, err := io.ReadAll(io.LimitReader(stream, 65537))
	if err != nil {
		return err
	}
	if len(raw) > 65536 {
		return fmt.Errorf("input exceeds 64 KiB")
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	var inputs []input
	if err := decoder.Decode(&inputs); err != nil {
		return err
	}
	var extra interface{}
	if err := decoder.Decode(&extra); err != io.EOF {
		return fmt.Errorf("expected one JSON array")
	}
	if len(inputs) < 1 || len(inputs) > 128 {
		return fmt.Errorf("expected 1..128 input pairs")
	}
	r := rt.New(io.Discard)
	defer r.Close(nil)
	thread := r.MainThread()
	chunk, err := r.CompileAndLoadLuaChunk("floor-reference", []byte(source), rt.TableValue(r.GlobalEnv()))
	if err != nil {
		return err
	}
	rows := make([]observation, 0, len(inputs))
	for _, pair := range inputs {
		if pair.A == nil || pair.B == nil {
			return fmt.Errorf("a and b must be int64 values")
		}
		row := observation{A: *pair.A, B: *pair.B}
		_, err = thread.CallContext(rt.RuntimeContextDef{HardLimits: rt.RuntimeResources{Cpu: 10000, Memory: 1 << 20}}, func() error {
			value, callErr := rt.Call1(thread, rt.FunctionValue(chunk), rt.IntValue(row.A), rt.IntValue(row.B))
			if callErr != nil {
				return callErr
			}
			quotient, ok := value.TryInt()
			if !ok {
				return fmt.Errorf("Lua result is not an integer")
			}
			row.Quotient = &quotient
			return nil
		})
		if err != nil {
			row.Error = err.Error()
		}
		rows = append(rows, row)
	}
	return json.NewEncoder(os.Stdout).Encode(rows)
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
}
