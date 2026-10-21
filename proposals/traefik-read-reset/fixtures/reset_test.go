package tcp

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"testing"
	"time"
)

type observation struct {
	OuterOp  string `json:"outer_op"`
	MiddleOp string `json:"middle_op"`
	InnerOp  string `json:"inner_op"`
	HasReset bool   `json:"has_reset"`
	HasError bool   `json:"has_error"`
}

func record(t *testing.T, id string, err error, want bool) {
	t.Helper()
	var operations []string
	for current := err; current != nil; current = errors.Unwrap(current) {
		if op, ok := current.(*net.OpError); ok {
			operations = append(operations, op.Op)
		}
	}
	if len(operations) > 3 {
		t.Fatal("error chain exceeds the bounded Gooo model")
	}
	var padded [3]string
	copy(padded[:], operations)
	actual := isReadConnResetError(err)
	level := func(value bool) string {
		if err == nil {
			return "NO_LOG"
		}
		if value {
			return "DEBUG"
		}
		return "ERROR"
	}
	message := ""
	if err != nil {
		message = err.Error()
	}
	row := struct {
		ID          string      `json:"id"`
		Observation observation `json:"observation"`
		Expected    string      `json:"expected"`
		Actual      string      `json:"actual"`
		Message     string      `json:"message"`
	}{id, observation{padded[0], padded[1], padded[2], errors.Is(err, resetErrno()), err != nil}, level(want), level(actual), message}
	data, marshalErr := json.Marshal(row)
	if marshalErr != nil {
		t.Fatal(marshalErr)
	}
	t.Logf("WITNESS %s", data)
	if actual != want {
		t.Errorf("classification = %t, want %t", actual, want)
	}
}

func TestReadResetClassification(t *testing.T) {
	op := func(name string, err error) error { return &net.OpError{Op: name, Net: "tcp", Err: err} }
	readReset := op("read", &os.SyscallError{Syscall: "read", Err: resetErrno()})
	writeReset := op("write", resetErrno())
	otherRead := op("read", errors.New("other read failure"))
	for _, tc := range []struct {
		name string
		err  error
		want bool
	}{
		{"nil", nil, false},
		{"plain-reset", resetErrno(), false},
		{"plain-other", errors.New("other failure"), false},
		{"read-reset", readReset, true},
		{"fmt-read-reset", fmt.Errorf("context: %w", readReset), true},
		{"write-reset", writeReset, false},
		{"dial-reset", op("dial", resetErrno()), false},
		{"read-other", otherRead, false},
		{"readfrom-read-reset", op("readfrom", readReset), true},
		{"writeto-read-reset", op("writeto", readReset), true},
		{"readfrom-writeto-read-reset", op("readfrom", op("writeto", readReset)), true},
		{"wrapped-readfrom-read-reset", fmt.Errorf("context: %w", op("readfrom", readReset)), true},
		{"readfrom-write-reset", op("readfrom", writeReset), false},
		{"readfrom-read-other", op("readfrom", otherRead), false},
		{"readfrom-reset-without-read", op("readfrom", resetErrno()), false},
	} {
		t.Run(tc.name, func(t *testing.T) { record(t, tc.name, tc.err, tc.want) })
	}
}

type readerOnly struct{ io.Reader }

func tcpPair(t *testing.T) (*net.TCPConn, *net.TCPConn) {
	t.Helper()
	listener, err := net.ListenTCP("tcp4", &net.TCPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = listener.Close() })
	client, err := net.DialTCP("tcp4", nil, listener.Addr().(*net.TCPAddr))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = client.Close() })
	server, err := listener.AcceptTCP()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = server.Close() })
	return client, server
}

func TestReadFromReset(t *testing.T) {
	client, source := tcpPair(t)
	destination, _ := tcpPair(t)
	if err := source.SetReadDeadline(time.Now().Add(2 * time.Second)); err != nil {
		t.Fatal(err)
	}
	if err := destination.SetWriteDeadline(time.Now().Add(2 * time.Second)); err != nil {
		t.Fatal(err)
	}
	if err := client.SetLinger(0); err != nil {
		t.Fatal(err)
	}
	if err := client.Close(); err != nil {
		t.Fatal(err)
	}
	// Hiding WriterTo exercises TCPConn.ReadFrom's wrapper around the source read error.
	_, err := io.Copy(destination, readerOnly{source})
	if !errors.Is(err, resetErrno()) {
		t.Fatal("expected a real peer reset", err)
	}
	outer, ok := err.(*net.OpError)
	if !ok || outer.Op != "readfrom" {
		t.Fatal("expected the ReadFrom operation context", err)
	}
	record(t, "loopback-reset", err, true)
}
