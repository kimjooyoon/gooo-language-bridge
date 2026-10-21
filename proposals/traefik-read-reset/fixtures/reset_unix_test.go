//go:build !windows

package tcp

import "syscall"

func resetErrno() error { return syscall.ECONNRESET }
