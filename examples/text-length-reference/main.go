// Observe string units with native Go library operations, independently of Gooo.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"unicode/utf16"
	"unicode/utf8"
)

type input struct {
	ID   string `json:"id"`
	Text string `json:"text"`
}

type lengths struct {
	UTF8Bytes  int `json:"utf8_bytes"`
	CodePoints int `json:"code_points"`
	UTF16Units int `json:"utf16_units"`
}

type observation struct {
	input
	Lengths lengths `json:"lengths"`
}

func run() error {
	decoder := json.NewDecoder(io.LimitReader(os.Stdin, 1<<20))
	decoder.DisallowUnknownFields()
	var inputs []input
	if err := decoder.Decode(&inputs); err != nil {
		return err
	}
	if err := decoder.Decode(new(any)); err != io.EOF {
		return fmt.Errorf("expected one JSON document")
	}
	if len(inputs) < 1 || len(inputs) > 128 {
		return fmt.Errorf("expected 1..128 inputs")
	}
	seen := map[string]bool{}
	results := make([]observation, 0, len(inputs))
	for _, row := range inputs {
		if row.ID == "" || seen[row.ID] || len(row.Text) > 1024 || !utf8.ValidString(row.Text) {
			return fmt.Errorf("invalid or duplicate input %q", row.ID)
		}
		seen[row.ID] = true
		results = append(results, observation{row, lengths{
			len(row.Text), utf8.RuneCountInString(row.Text), len(utf16.Encode([]rune(row.Text))),
		}})
	}
	return json.NewEncoder(os.Stdout).Encode(results)
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
