package main

import (
	"encoding/json"
	"os"
	"runtime"
	"runtime/debug"
	"strconv"

	"github.com/pelletier/go-toml/v2"
)

func main() {
	debug.SetMaxStack(8 << 20)
	debug.SetMemoryLimit(32 << 20)
	if len(os.Args) != 2 {
		os.Exit(64)
	}
	name := os.Args[1]
	var document map[string]interface{}
	switch name {
	case "ordinary-map":
		document = map[string]interface{}{"answer": int64(7)}
	case "self-map":
		document = map[string]interface{}{"leaf": ""}
		document["self"] = document
	case "shared-acyclic-pointer":
		var leaf interface{} = int64(7)
		shared := &leaf
		document = map[string]interface{}{"a": shared, "b": shared}
	case "nil-values":
		var pointer *int
		document = map[string]interface{}{"nil_interface": nil, "nil_pointer": pointer}
	case "pointer-interface-cycle":
		var value interface{}
		value = &value
		document = map[string]interface{}{"self": value}
	default:
		os.Exit(64)
	}
	output := json.NewEncoder(os.Stdout)
	if err := output.Encode(map[string]interface{}{
		"phase": "call_start", "case": name, "go": runtime.Version(),
		"os": runtime.GOOS, "arch": runtime.GOARCH, "int_bits": strconv.IntSize,
		"stack_limit_bytes": 8 << 20, "memory_limit_bytes": 32 << 20,
		"memory_limit_kind": "soft",
	}); err != nil {
		os.Exit(65)
	}
	encoded, err := toml.Marshal(document)
	result := map[string]interface{}{"phase": "returned", "case": name, "encoded": string(encoded)}
	if err != nil {
		result["error"] = err.Error()
	} else {
		result["error"] = ""
		var decoded map[string]interface{}
		if err := toml.Unmarshal(encoded, &decoded); err != nil {
			result["decode_error"] = err.Error()
		} else {
			result["decoded"] = decoded
		}
	}
	if err := output.Encode(result); err != nil {
		os.Exit(65)
	}
}
