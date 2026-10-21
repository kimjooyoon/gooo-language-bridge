package textarea

import (
	"encoding/json"
	"testing"

	tea "charm.land/bubbletea/v2"
)

func TestBridgeForwardDelete(t *testing.T) {
	for _, tc := range []struct {
		id   string
		text string
		col  int
		want string
	}{
		{"last-character", "ab\ncd", 1, "a\ncd"},
		{"only-character", "a\nb", 0, "\nb"},
		{"wide-character", "a界\n다", 1, "a\n다"},
		{"middle-character", "abc\ncd", 1, "ac\ncd"},
		{"line-end", "ab\ncd", 2, "abcd"},
		{"empty-line", "\ncd", 0, "cd"},
		{"last-line-character", "ab", 1, "a"},
		{"last-line-end", "ab", 2, "ab"},
	} {
		t.Run(tc.id, func(t *testing.T) {
			m := New()
			m.Focus()
			m.SetValue(tc.text)
			if m.Line() > 0 {
				m.CursorUp()
			}
			m.SetCursorColumn(tc.col)
			if m.Line() != 0 || m.col != tc.col || m.Value() != tc.text {
				t.Fatal("input or cursor differs")
			}
			byteColumn := len(string(m.value[m.row][:m.col]))
			m, _ = m.Update(tea.KeyPressMsg{Code: tea.KeyDelete})
			witness, err := json.Marshal(map[string]any{
				"id": tc.id, "input": map[string]any{"text": tc.text, "byte_column": byteColumn},
				"rune_column": tc.col, "expected": tc.want, "actual": m.Value(),
			})
			if err != nil {
				t.Fatal(err)
			}
			t.Logf("WITNESS %s", witness)
			if got := m.Value(); got != tc.want {
				t.Errorf("Delete at column %d in %q = %q; want %q", tc.col, tc.text, got, tc.want)
			}
		})
	}
}
