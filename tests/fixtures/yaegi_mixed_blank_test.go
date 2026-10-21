package interp_test

import (
	"github.com/traefik/yaegi/interp"
	"testing"
)

func TestKnownMixedBlankAssignments(t *testing.T) {
	want := func() int {
		n := 3
		_ = n + 1
		_ = -n
		_ = !(n == 3)
		return n
	}()
	t.Logf("native Go reference = %d", want)
	i := interp.New(interp.Options{})
	if _, err := i.Eval(`package p
func Discard() int {
 n := 3
 _ = n + 1
 _ = -n
 _ = !(n == 3)
 return n
}`); err != nil {
		t.Fatal(err)
	}
	value, err := i.Eval("p.Discard()")
	if err != nil {
		t.Fatal(err)
	}
	if value.Interface() != want {
		t.Errorf("Discard() = %v, want %d", value.Interface(), want)
	}
}
