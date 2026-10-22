package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"runtime"
	"runtime/debug"

	"github.com/d5/tengo/v2"
)

const source = `settings := {a: 0, b: 1, enabled: true}
for key, value in overrides {
    settings[key] = value
}
resolved_a := settings.a
resolved_b := settings.b
resolved_enabled := settings.enabled
`

type input struct {
	ID        string                     `json:"id"`
	Overrides map[string]json.RawMessage `json:"overrides"`
}
type settings struct {
	A       int64 `json:"a"`
	B       int64 `json:"b"`
	Enabled bool  `json:"enabled"`
}
type observation struct {
	ID        string                 `json:"id"`
	Overrides map[string]interface{} `json:"overrides"`
	Actual    settings               `json:"actual"`
}

func run() error {
	if len(os.Args) == 2 && os.Args[1] == "--identity" {
		identity := map[string]string{"go": runtime.Version(), "os": runtime.GOOS, "arch": runtime.GOARCH, "tengo_source": source}
		if info, ok := debug.ReadBuildInfo(); ok {
			for _, d := range info.Deps {
				if d.Path == "github.com/d5/tengo/v2" {
					if d.Replace != nil {
						return fmt.Errorf("unexpected Tengo module replacement")
					}
					identity["module"], identity["version"], identity["sum"] = d.Path, d.Version, d.Sum
				}
			}
		}
		return json.NewEncoder(os.Stdout).Encode(identity)
	}
	var stream io.Reader = os.Stdin
	if len(os.Args) == 3 && os.Args[1] == "--input" {
		f, err := os.Open(os.Args[2])
		if err != nil {
			return err
		}
		defer f.Close()
		stream = f
	} else if len(os.Args) != 1 {
		return fmt.Errorf("expected --identity, --input FILE or standard input")
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
	if err = decoder.Decode(&inputs); err != nil {
		return err
	}
	var extra interface{}
	if decoder.Decode(&extra) != io.EOF {
		return fmt.Errorf("expected one JSON array")
	}
	if len(inputs) < 1 || len(inputs) > 64 {
		return fmt.Errorf("expected 1..64 input cases")
	}
	seen := map[string]bool{}
	maps := make([]map[string]interface{}, len(inputs))
	for i, in := range inputs {
		if in.ID == "" || len(in.ID) > 64 || seen[in.ID] || in.Overrides == nil {
			return fmt.Errorf("invalid or duplicate case identity/map")
		}
		seen[in.ID] = true
		values := map[string]interface{}{}
		for key, value := range in.Overrides {
			if bytes.Equal(bytes.TrimSpace(value), []byte("null")) {
				return fmt.Errorf("null override is outside this observer's domain")
			}
			switch key {
			case "a", "b":
				var v int64
				if err = json.Unmarshal(value, &v); err != nil {
					return err
				}
				values[key] = v
			case "enabled":
				var v bool
				if err = json.Unmarshal(value, &v); err != nil {
					return err
				}
				values[key] = v
			default:
				return fmt.Errorf("unknown override field: %s", key)
			}
		}
		maps[i] = values
	}
	script := tengo.NewScript([]byte(source))
	if err = script.Add("overrides", map[string]interface{}{}); err != nil {
		return err
	}
	compiled, err := script.Compile()
	if err != nil {
		return err
	}
	rows := make([]observation, 0, len(inputs))
	for i, in := range inputs {
		if err = compiled.Set("overrides", maps[i]); err != nil {
			return err
		}
		if err = compiled.Run(); err != nil {
			return err
		}
		a, aOK := compiled.Get("resolved_a").Value().(int64)
		b, bOK := compiled.Get("resolved_b").Value().(int64)
		enabled, eOK := compiled.Get("resolved_enabled").Value().(bool)
		if !aOK || !bOK || !eOK {
			return fmt.Errorf("unexpected native output type")
		}
		rows = append(rows, observation{in.ID, maps[i], settings{a, b, enabled}})
	}
	return json.NewEncoder(os.Stdout).Encode(rows)
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
}
