package main

import (
	"encoding/json"
	"fmt"
	"go/scanner"
	"go/token"
	"os"
	"strings"

	"github.com/alecthomas/chroma/v3/lexers"
)

func main() {
	raw, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}
	type tok struct {
		Type  string `json:"type"`
		Value string `json:"value"`
	}
	type row struct {
		Literal string `json:"literal"`
		Native  []tok  `json:"native"`
		Chroma  []tok  `json:"chroma"`
	}
	rows := []row{}
	for _, literal := range strings.Fields(string(raw)) {
		r := row{Literal: literal}
		var s scanner.Scanner
		s.Init(token.NewFileSet().AddFile("literal.go", -1, len(literal)), []byte(literal), func(_ token.Position, msg string) { panic(msg) }, 0)
		for {
			_, t, v := s.Scan()
			if t == token.EOF {
				break
			}
			if t != token.SEMICOLON {
				r.Native = append(r.Native, tok{t.String(), v})
			}
		}
		it, err := lexers.Go.Tokenise(nil, literal)
		if err != nil {
			panic(err)
		}
		for t := range it {
			r.Chroma = append(r.Chroma, tok{t.Type.String(), t.Value})
		}
		rows = append(rows, r)
	}
	if err := json.NewEncoder(os.Stdout).Encode(rows); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
