package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"strings"
	"testing"

	"github.com/alecthomas/chroma/v2"
)

func TestJSONKeepsRawStringsAndLineEndings(t *testing.T) {
	for _, newline := range []string{"\n", "\r\n", "\r"} {
		t.Run(fmtName(newline), func(t *testing.T) {
			text := "activity 인사(Text) -> Text computes `// # /* raw" + newline + "return input`" + newline
			var output bytes.Buffer
			if err := run([]string{"-format", "json", "-"}, strings.NewReader(text), &output, io.Discard); err != nil {
				t.Fatal(err)
			}
			var tokens []chroma.Token
			if err := json.Unmarshal(output.Bytes(), &tokens); err != nil {
				t.Fatal(err)
			}
			var restored strings.Builder
			raw := false
			for _, token := range tokens {
				restored.WriteString(token.Value)
				if strings.Contains(token.Value, "// # /* raw") {
					raw = token.Type == chroma.LiteralStringBacktick
				}
			}
			if restored.String() != text || !raw {
				t.Fatal("source bytes or raw-string token boundary changed")
			}
		})
	}
}

func fmtName(newline string) string {
	return strings.NewReplacer("\r", "CR", "\n", "LF").Replace(newline)
}

func TestHTMLIsSelfContainedAndEscapesSource(t *testing.T) {
	var output bytes.Buffer
	if err := render("entity Text id \"<script>alert(1)</script>\"\n", "html", &output); err != nil {
		t.Fatal(err)
	}
	page := output.String()
	if strings.Contains(page, "<script>") || !strings.Contains(page, "&lt;script&gt;") || !strings.Contains(page, "</html>") {
		t.Fatal("expected a complete HTML page with escaped source")
	}
}

type failedWriter struct{}

func (failedWriter) Write([]byte) (int, error) { return 0, io.ErrClosedPipe }

func TestErrorsAreReturned(t *testing.T) {
	for _, test := range []struct{ text, format string }{
		{"entity Text", "unknown"}, {"\xff", "json"}, {"?", "html"},
	} {
		var output bytes.Buffer
		if err := render(test.text, test.format, &output); err == nil || output.Len() != 0 {
			t.Fatal("invalid input should fail before output")
		}
	}
	for _, format := range []string{"html", "json"} {
		if err := render("entity Text\n", format, failedWriter{}); !errors.Is(err, io.ErrClosedPipe) {
			t.Fatalf("output error was lost for %s: %v", format, err)
		}
	}
	if err := run([]string{"-"}, strings.NewReader(strings.Repeat(" ", maxSourceBytes+1)), io.Discard, io.Discard); err == nil {
		t.Fatal("oversized source accepted")
	}
}

func TestLexerMatchesSubmittedSource(t *testing.T) {
	var provenance struct {
		SHA256 string `json:"sha256"`
	}
	data, err := os.ReadFile("provenance.json")
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(data, &provenance); err != nil {
		t.Fatal(err)
	}
	xml, err := source.ReadFile("gooo.xml")
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(xml)
	if hex.EncodeToString(digest[:]) != provenance.SHA256 {
		t.Fatal("bundled lexer differs from its recorded source")
	}
}
