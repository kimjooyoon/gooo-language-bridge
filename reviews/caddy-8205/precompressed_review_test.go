// Copyright 2015 Matthew Holt and The Caddy Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package fileserver

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"mime"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"testing"

	"github.com/caddyserver/caddy/v2"
	"github.com/caddyserver/caddy/v2/modules/caddyhttp"
	"github.com/caddyserver/caddy/v2/modules/caddyhttp/encode"
)

// Full 200 and single-range 206 responses are covered by TestPrecompressedRangeResponse.
func TestPrecompressedServeContentResponseHeaders(t *testing.T) {
	root := t.TempDir()
	body := []byte("original response body")
	sidecar := gzipBytes(t, body)
	for name, data := range map[string][]byte{"f.txt": body, "f.txt.gz": sidecar} {
		if err := os.WriteFile(filepath.Join(root, name), data, 0o600); err != nil {
			t.Fatal(err)
		}
	}

	for _, tc := range []struct {
		name, method, header, value, ifRange string
		override                             caddyhttp.WeakString
		wantStatus                           int
		wantBody                             string
	}{
		{name: "mismatched If-Match", header: "If-Match", value: `"other"`, wantStatus: http.StatusPreconditionFailed, wantBody: "empty"},
		{name: "mismatched If-Match overridden to 200", header: "If-Match", value: `"other"`, override: "200", wantStatus: http.StatusOK, wantBody: "empty"},
		{name: "matching If-None-Match", header: "If-None-Match", value: `"current"`, wantStatus: http.StatusNotModified, wantBody: "empty"},
		{name: "matching If-None-Match overridden to 200", header: "If-None-Match", value: `"current"`, override: "200", wantStatus: http.StatusOK, wantBody: "empty"},
		{name: "HEAD", method: http.MethodHead, wantStatus: http.StatusOK, wantBody: "head"},
		{name: "mismatched If-Range", header: "Range", value: "bytes=0-3", ifRange: `"other"`, wantStatus: http.StatusOK, wantBody: "full"},
		{name: "unsatisfiable range", header: "Range", value: fmt.Sprintf("bytes=%d-", len(sidecar)), wantStatus: http.StatusRequestedRangeNotSatisfiable, wantBody: "error"},
		{name: "multipart range", header: "Range", value: "bytes=0-3,8-11", wantStatus: http.StatusPartialContent, wantBody: "multipart"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			fsrv := FileServer{
				Root:               root,
				CanonicalURIs:      new(bool),
				PrecompressedOrder: []string{"gzip"},
				StatusCode:         tc.override,
			}
			ctx, cancel := caddy.NewContext(caddy.Context{Context: context.Background()})
			t.Cleanup(cancel)
			if err := fsrv.Provision(ctx); err != nil {
				t.Fatal(err)
			}
			fsrv.precompressors = map[string]encode.Precompressed{
				"gzip": testPrecompressed{encoding: "gzip", suffix: ".gz"},
			}
			r := newPrecompressedRequest(t, "/f.txt")
			if tc.method != "" {
				r.Method = tc.method
			}
			r.Header.Set("Accept-Encoding", "gzip")
			if tc.header != "" {
				r.Header.Set(tc.header, tc.value)
			}
			if tc.ifRange != "" {
				r.Header.Set("If-Range", tc.ifRange)
			}
			w := httptest.NewRecorder()
			w.Header().Set("Etag", `"current"`)
			if err := fsrv.ServeHTTP(w, r, nil); err != nil {
				t.Fatal(err)
			}

			// Inspect the committed headers, not the mutable map after ServeHTTP returns.
			response := w.Result()
			defer response.Body.Close()
			if response.StatusCode != tc.wantStatus {
				t.Fatalf("status = %d, want %d", response.StatusCode, tc.wantStatus)
			}
			if got := response.Header.Get("Vary"); got != "Accept-Encoding" {
				t.Errorf("Vary = %q, want Accept-Encoding", got)
			}
			if tc.wantBody == "empty" || tc.wantBody == "error" {
				if got := response.Header.Get("Content-Encoding"); got != "" {
					t.Errorf("Content-Encoding = %q on a non-content response, want unset", got)
				}
				if got := response.Header.Get("Content-Length"); got != "" {
					// A standard error-body length is valid; the sidecar length is not.
					if got == strconv.Itoa(len(sidecar)) || got != strconv.Itoa(w.Body.Len()) {
						t.Errorf("Content-Length = %q, body length = %d, sidecar length = %d", got, w.Body.Len(), len(sidecar))
					}
				}
				if tc.wantBody == "empty" && w.Body.Len() != 0 {
					t.Errorf("conditional response body = %q, want empty", w.Body.Bytes())
				}
				if tc.wantBody == "error" {
					if w.Body.Len() == 0 || bytes.Equal(w.Body.Bytes(), sidecar) {
						t.Errorf("range error body = %q, want an error response", w.Body.Bytes())
					}
					if got, want := response.Header.Get("Content-Range"), fmt.Sprintf("bytes */%d", len(sidecar)); got != want {
						t.Errorf("Content-Range = %q, want %q", got, want)
					}
				}
				return
			}

			if got := response.Header.Get("Content-Encoding"); got != "gzip" {
				t.Errorf("Content-Encoding = %q, want gzip", got)
			}
			if tc.wantBody == "full" || tc.wantBody == "head" {
				if got := response.Header.Get("Content-Length"); got != strconv.Itoa(len(sidecar)) {
					t.Errorf("Content-Length = %q, want sidecar length %d", got, len(sidecar))
				}
				if got := response.Header.Get("Content-Range"); got != "" {
					t.Errorf("Content-Range = %q on a full response, want unset", got)
				}
				if tc.wantBody == "head" {
					if w.Body.Len() != 0 {
						t.Errorf("HEAD body = %q, want empty", w.Body.Bytes())
					}
				} else if !bytes.Equal(w.Body.Bytes(), sidecar) {
					t.Errorf("full body = %x, want sidecar %x", w.Body.Bytes(), sidecar)
				}
				return
			}
			if got := response.Header.Get("Content-Length"); got != strconv.Itoa(w.Body.Len()) {
				t.Errorf("Content-Length = %q, want multipart body length %d", got, w.Body.Len())
			}
			mediaType, params, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
			if err != nil || mediaType != "multipart/byteranges" {
				t.Fatalf("Content-Type = %q, error = %v", response.Header.Get("Content-Type"), err)
			}
			parts := multipart.NewReader(bytes.NewReader(w.Body.Bytes()), params["boundary"])
			for _, interval := range [][2]int{{0, 3}, {8, 11}} {
				part, err := parts.NextPart()
				if err != nil {
					t.Fatal(err)
				}
				wantRange := fmt.Sprintf("bytes %d-%d/%d", interval[0], interval[1], len(sidecar))
				if got := part.Header.Get("Content-Range"); got != wantRange {
					t.Errorf("part Content-Range = %q, want %q", got, wantRange)
				}
				data, err := io.ReadAll(part)
				if err != nil || !bytes.Equal(data, sidecar[interval[0]:interval[1]+1]) {
					t.Fatalf("range body = %x, error = %v", data, err)
				}
			}
			if _, err := parts.NextPart(); err != io.EOF {
				t.Fatalf("after two ranges: error = %v, want EOF", err)
			}
		})
	}
}
