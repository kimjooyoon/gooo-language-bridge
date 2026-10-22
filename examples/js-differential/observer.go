package main

import (
	"encoding/json"
	"fmt"
	"os"
	"runtime"
	"strconv"
	"time"

	"github.com/dop251/goja"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
}

func run() error {
	if len(os.Args) == 2 && os.Args[1] == "--identity" {
		return json.NewEncoder(os.Stdout).Encode(map[string]string{"go": runtime.Version(), "os": runtime.GOOS, "arch": runtime.GOARCH})
	}
	if len(os.Args) != 3 {
		return fmt.Errorf("expected script and timeout milliseconds")
	}
	ms, err := strconv.Atoi(os.Args[2])
	if err != nil || ms < 1 || ms > 60000 {
		return fmt.Errorf("invalid timeout")
	}
	source, err := os.ReadFile(os.Args[1])
	if err != nil {
		return err
	}
	vm := goja.New()
	timer := time.AfterFunc(time.Duration(ms)*time.Millisecond, func() { vm.Interrupt("deadline exceeded") })
	defer timer.Stop()
	value, err := vm.RunString(string(source))
	if err != nil {
		return err
	}
	text, ok := value.(goja.String)
	if !ok {
		return fmt.Errorf("script must return a JSON string")
	}
	// Reject raw unpaired units before Go's UTF-8 conversion could replace them.
	for i := 0; i < text.Length(); i++ {
		c := text.CharAt(i)
		if c >= 0xd800 && c <= 0xdbff {
			i++
			if i >= text.Length() || text.CharAt(i) < 0xdc00 || text.CharAt(i) > 0xdfff {
				return fmt.Errorf("unpaired surrogate in JSON transport")
			}
		} else if c >= 0xdc00 && c <= 0xdfff {
			return fmt.Errorf("unpaired surrogate in JSON transport")
		}
	}
	raw := text.String()
	if !json.Valid([]byte(raw)) {
		return fmt.Errorf("script returned invalid JSON")
	}
	_, err = fmt.Fprintln(os.Stdout, raw)
	return err
}
