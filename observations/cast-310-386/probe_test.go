// Copyright 2026 Gooo Language Bridge contributors.
// SPDX-License-Identifier: MIT

package cast_test

import (
	"encoding/json"
	"runtime"
	"strconv"
	"testing"

	"github.com/spf13/cast"
)

func TestBridge386Runtime(t *testing.T) {
	data, err := json.Marshal(struct {
		GoVersion string `json:"go_version"`
		OS        string `json:"os"`
		Arch      string `json:"arch"`
		IntBits   int    `json:"int_bits"`
	}{runtime.Version(), runtime.GOOS, runtime.GOARCH, strconv.IntSize})
	if err != nil {
		t.Fatal(err)
	}
	t.Logf("CAST386_RUNTIME %s", data)
	if runtime.GOOS != "linux" || runtime.GOARCH != "386" || strconv.IntSize != 32 {
		t.Fatalf("requires compiled linux/386 runtime with 32-bit int, got %s/%s with %d-bit int",
			runtime.GOOS, runtime.GOARCH, strconv.IntSize)
	}
}

func TestBridge386Bounds(t *testing.T) {
	toInt := func(input string) (string, error) {
		value, err := cast.ToIntE(input)
		return strconv.FormatInt(int64(value), 10), err
	}
	toUint := func(input string) (string, error) {
		value, err := cast.ToUintE(input)
		return strconv.FormatUint(uint64(value), 10), err
	}
	toInt64 := func(input string) (string, error) {
		value, err := cast.ToInt64E(input)
		return strconv.FormatInt(value, 10), err
	}
	toUint64 := func(input string) (string, error) {
		value, err := cast.ToUint64E(input)
		return strconv.FormatUint(value, 10), err
	}
	for _, tt := range []struct {
		name, input, want string
		convert           func(string) (string, error)
		wantError         bool
	}{
		{"int/min", "-2147483648", "-2147483648", toInt, false},
		{"int/max", "2147483647", "2147483647", toInt, false},
		{"int/overflow", "2147483648", "", toInt, true},
		{"int/underflow", "-2147483649", "", toInt, true},
		{"uint/max", "4294967295", "4294967295", toUint, false},
		{"uint/overflow", "4294967296", "", toUint, true},
		{"int64/min", "-9223372036854775808", "-9223372036854775808", toInt64, false},
		{"int64/max", "9223372036854775807", "9223372036854775807", toInt64, false},
		{"uint64/max", "18446744073709551615", "18446744073709551615", toUint64, false},
	} {
		t.Run(tt.name, func(t *testing.T) {
			value, err := tt.convert(tt.input)
			t.Logf("input=%q value=%s error=%v", tt.input, value, err)
			if tt.wantError {
				if err == nil {
					t.Fatalf("conversion of %q returned %s without an error", tt.input, value)
				}
				return
			}
			if err != nil {
				t.Fatalf("conversion of %q failed: %v", tt.input, err)
			}
			if value != tt.want {
				t.Errorf("conversion of %q = %s, want %s", tt.input, value, tt.want)
			}
		})
	}
}
