package main

import (
	"io"
	"strings"
	"testing"
)

func BenchmarkRejectInvalidSource(b *testing.B) {
	text := strings.Repeat("?", 128<<10)
	b.ReportAllocs()
	b.ResetTimer()
	for n := 0; n < b.N; n++ {
		if err := render(text, "json", io.Discard); err == nil {
			b.Fatal("invalid source was accepted")
		}
	}
}
