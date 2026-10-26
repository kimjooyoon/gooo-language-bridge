# Existing gojq Iter behavior for the RunSeq discussion

This small observer supports the maintainer's [request for thoughts on RunSeq and RunSeqWithContext](https://github.com/itchyny/gojq/issues/262#issuecomment-4015089249). It executes the existing public Iter API at [56ae40d64ce0f4824803e789704e1a1a49293642](https://github.com/itchyny/gojq/commit/56ae40d64ce0f4824803e789704e1a1a49293642).

It does not implement or execute the proposed Seq2 methods, assess an unpublished patch, or claim upstream acceptance. The [existing library documentation](https://github.com/itchyny/gojq/blob/56ae40d64ce0f4824803e789704e1a1a49293642/README.md#usage-as-a-library) explains continuing after errors and caller handling of HaltError.

## Observed behavior

- Iterating `[1, "first", null, "second", 2][] | if type == "string" then error(.) else . end` produces five events: value 1, error, null, error, value 2.
- `empty` produces no events. Null is a value, not exhaustion.
- Deliberately continuing `1, halt, 2` retains a concrete `*gojq.HaltError` with nil payload and then produces 2. This illustrates the current library's caller choice; it is not a recommendation to ignore halting errors.
- A missing variable binding and an already-canceled context are each emitted as an error event.
- Consuming the same `1, 2` iterator again produces nothing; a new Code.Run produces 1, 2.
- A counted input iterator over 10, 20, 30 has exactly one Next call after the first output. A new execution of the same compiled `inputs` query then consumes 20 and 30, followed by the source's end check. A new execution does not rewind the configured input iterator.

These observations motivate preserving values/errors/null and documenting the lifetime of the proposed returned sequence. They do not establish how that not-yet-published API will behave. Go's [single-use iterator guidance](https://pkg.go.dev/iter#hdr-Single_Use_Iterators) permits a documented single-use stream; [Seq2](https://pkg.go.dev/iter#Seq2) requires stopping when yield returns false. No Seq2 callback was exercised by this observer.

## Reproduce

With the pinned gojq source checked out in a directory and `observer.go` stored outside it, run from the source directory:

```sh
GOTOOLCHAIN=local GOWORK=off GOENV=off GOPROXY=off \
  GOMAXPROCS=2 GOMEMLIMIT=128MiB \
  go run -mod=readonly -p=2 /path/to/observer.go
```

The recorded environment used already-installed Go 1.27.3 and cached dependencies; GOPROXY=off means this command will refuse missing downloads. The observer stops after at most 20 Next calls per collection and uses only finite inputs. The recording supervisor imposed a 60-second subprocess deadline and verified its process group was gone. GOMEMLIMIT is a soft runtime target, not a hard memory cap. Both observed executions completed normally, totaling about 2.034 seconds including compilation; no SDK/dependency download, full suite, race run, benchmark, or conformance run was performed.

## Original evidence and initial correction

`native.stdout` and `native.stderr` are the original final output streams. `observer.go` is their exact source; `capture.json` is a portable projection of the private process records, and `validation.json` records the bounded checks. Hashes bind file contents, not author identity.

`initial/` preserves the first observer and output. Its simple comma chain (`1, error("first"), null, error("second"), 2`) produced only 1, the first error, and 2, so it did not exercise the intended null/two-error scenario. The revised array-iteration query separates those branches. This is a correction to the chosen example, not a newly reported library defect; the initial output was not discarded.

The observer was independently authored for this discussion. gojq remains a separate MIT-licensed dependency and its source was unmodified. AI assistance was used.
