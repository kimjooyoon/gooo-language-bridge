package main

import (
	"bytes"
	"embed"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"unicode/utf8"

	"github.com/alecthomas/chroma/v2"
	"github.com/alecthomas/chroma/v2/formatters/html"
	"github.com/alecthomas/chroma/v2/styles"
)

//go:embed gooo.xml
var source embed.FS

const maxSourceBytes = 4 << 20

type stopOnErrorLexer struct {
	chroma.Lexer
	err error
}

func (l *stopOnErrorLexer) Tokenise(options *chroma.TokeniseOptions, text string) (chroma.Iterator, error) {
	iterator, err := l.Lexer.Tokenise(options, text)
	if err != nil {
		return nil, err
	}
	return func() chroma.Token {
		if l.err != nil {
			return chroma.EOF
		}
		token := iterator()
		if token.Type == chroma.Error {
			l.err = fmt.Errorf("unrecognised source character %q", token.Value)
			return chroma.EOF
		}
		return token
	}, nil
}

func render(text, format string, output io.Writer) error {
	if format != "html" && format != "json" {
		return fmt.Errorf("unknown format %q (use html or json)", format)
	}
	if !utf8.ValidString(text) {
		return errors.New("source must be valid UTF-8")
	}
	lexer, err := chroma.NewXMLLexer(source, "gooo.xml")
	if err != nil {
		return err
	}
	// Gooo raw strings preserve original line endings.
	// Reject raw Error tokens before Coalesce reads ahead across an invalid run.
	checked := &stopOnErrorLexer{Lexer: lexer}
	iterator, err := chroma.Coalesce(checked).Tokenise(&chroma.TokeniseOptions{State: "root", EnsureLF: false}, text)
	if err != nil {
		return err
	}
	tokens := iterator.Tokens()
	if checked.err != nil {
		return checked.err
	}
	var original strings.Builder
	for _, token := range tokens {
		original.WriteString(token.Value)
	}
	if original.String() != text {
		return errors.New("token stream changed the source")
	}
	if format == "json" {
		return json.NewEncoder(output).Encode(tokens)
	}
	// The released formatter can ignore writer errors; only write the finished page to the caller.
	var page bytes.Buffer
	if err := html.New(html.Standalone(true)).Format(&page, styles.Get("github"), chroma.Literator(tokens...)); err != nil {
		return err
	}
	_, err = page.WriteTo(output)
	return err
}

func run(args []string, input io.Reader, output, diagnostics io.Writer) error {
	options := flag.NewFlagSet("highlight-gooo", flag.ContinueOnError)
	options.SetOutput(diagnostics)
	format := options.String("format", "html", "output format: html or json")
	if err := options.Parse(args); err != nil {
		return err
	}
	if options.NArg() != 1 {
		return errors.New("usage: highlight-gooo [-format html|json] source.gooo (or - for stdin)")
	}
	if path := options.Arg(0); path != "-" {
		file, err := os.Open(path)
		if err != nil {
			return err
		}
		defer file.Close()
		input = file
	}
	data, err := io.ReadAll(io.LimitReader(input, maxSourceBytes+1))
	if err != nil {
		return err
	}
	if len(data) > maxSourceBytes {
		return errors.New("source exceeds the 4 MiB limit")
	}
	return render(string(data), *format, output)
}

func main() {
	if err := run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr); err != nil && !errors.Is(err, flag.ErrHelp) {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
