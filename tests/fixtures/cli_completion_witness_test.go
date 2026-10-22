package cli_test

import (
	"context"
	"encoding/json"
	"io"
	"reflect"
	"testing"

	"github.com/urfave/cli/v3"
)

func TestBridgeCompletionIntent(t *testing.T) {
	type input struct {
		Token      string `json:"token"`
		Completion bool   `json:"completion"`
		Incomplete bool   `json:"incomplete"`
	}
	type sample struct {
		id   string
		args []string
		in   input
		want string
	}
	samples := []sample{}
	for _, scope := range []string{"root", "child", "nested"} {
		for _, c := range []struct{ name, token string }{
			{"unknown", "-az"}, {"missing-ascii", "-ab"}, {"missing-unicode", "-a한"}, {"single-missing", "-b"},
		} {
			samples = append(samples, sample{scope + "/" + c.name, []string{c.token}, input{c.token, true, true}, "PENDING:" + c.token})
		}
	}
	for _, c := range []struct {
		name                 string
		args                 []string
		complete, incomplete bool
		want                 string
	}{
		{"reject-unknown", []string{"-az"}, false, true, "REJECT"},
		{"reject-missing", []string{"-ab"}, false, true, "REJECT"},
		{"reject-unicode", []string{"-a한"}, false, true, "REJECT"},
		{"equals-value", []string{"-ab=given"}, false, false, "CONSUMED"},
		{"separate-value", []string{"-ab", "given"}, false, false, "CONSUMED"},
		{"equals-empty", []string{"-ab="}, false, false, "CONSUMED"},
		{"complete-value", []string{"-ab=given"}, true, false, "CONSUMED"},
		{"complete-empty", []string{"-ab="}, true, false, "CONSUMED"},
	} {
		samples = append(samples, sample{"control/" + c.name, c.args, input{c.args[0], c.complete, c.incomplete}, c.want})
	}
	for _, c := range samples {
		t.Run(c.id, func(t *testing.T) {
			action, completed := false, false
			var got []string
			newCommand := func(name string) *cli.Command {
				return &cli.Command{
					Name:          name,
					Flags:         []cli.Flag{&cli.BoolFlag{Name: "a"}, &cli.StringFlag{Name: "b"}, &cli.StringFlag{Name: "한"}},
					Action:        func(context.Context, *cli.Command) error { action = true; return nil },
					ShellComplete: func(_ context.Context, cmd *cli.Command) { completed = true; got = cmd.Args().Slice() },
				}
			}
			root, child, nested := newCommand("app"), newCommand("sub"), newCommand("nested")
			root.EnableShellCompletion = c.in.Completion
			root.UseShortOptionHandling = true
			root.Writer = io.Discard
			root.ErrWriter = io.Discard
			root.Commands = []*cli.Command{child}
			child.Commands = []*cli.Command{nested}
			args := []string{"app"}
			if c.id[:5] == "child" {
				args = append(args, "sub")
			}
			if c.id[:6] == "nested" {
				args = append(args, "sub", "nested")
			}
			args = append(args, "value")
			args = append(args, c.args...)
			if c.in.Completion {
				args = append(args, "--generate-shell-completion")
			}
			err := root.Run(t.Context(), args)
			actual := "CONSUMED"
			if err != nil {
				actual = "REJECT"
			} else if c.in.Completion {
				if !completed || action {
					actual = "INVALID_CALLBACK"
				} else if reflect.DeepEqual(got, []string{"value", c.in.Token}) {
					actual = "PENDING:" + c.in.Token
				} else if !reflect.DeepEqual(got, []string{"value"}) {
					actual = "INVALID_TAIL"
				}
			} else if !action || completed {
				actual = "INVALID_CALLBACK"
			}
			witness, marshalErr := json.Marshal(map[string]any{"id": c.id, "input": c.in, "argv": args, "completion_args": got, "action": action, "completed": completed, "error": err != nil, "expected": c.want, "actual": actual})
			if marshalErr != nil {
				t.Fatal(marshalErr)
			}
			t.Logf("WITNESS %s", witness)
			if actual != c.want {
				t.Errorf("input result=%q want=%q", actual, c.want)
			}
		})
	}
}
