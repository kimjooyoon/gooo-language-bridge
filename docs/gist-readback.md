# Check saved Gist file bytes

A saved API text field can differ from the file bytes bound to a Gist commit.
During a GoAWK review, a captured `original-pr.patch` text field held 4,621 bytes,
while the requested commit's blob held the expected 4,624 bytes. The difference
was an escaped Unicode sequence. The capture does not establish where the text
changed; it is not evidence of a GitHub defect. The original publication was
correct and did not need another POST or PATCH.

`tools/check_gist_readback.py` compares a complete expected manifest with saved
API JSON and saved Git objects. It checks the requested commit, its flat tree,
each filename-to-blob link and exact content hashes. It records API text
differences separately from the verified Git bytes. It makes no network request,
runs no Git command or captured source, and never recommends reposting.

## Try the synthetic example

Python 3.9+ is sufficient. These IDs, timestamps, objects and API fields are
**synthetic**, not a real publication or GitHub capture. From the repository root:

```sh
python3 examples/gist-readback/make_example.py --out /tmp/gist-readback-example
python3 tools/check_gist_readback.py \
  --gist https://gist.github.com/example/11111111111111111111111111111111 \
  --revision "$(cat /tmp/gist-readback-example/revision.txt)" \
  --manifest /tmp/gist-readback-example/expected.json \
  --api /tmp/gist-readback-example/api.json \
  --objects /tmp/gist-readback-example/objects.batch \
  --out /tmp/gist-readback-checked
```

Expect exit 0, `GIT_BLOBS_MATCH_API_TEXT_DIFFERS`, two matching Git files, and
`artifact.txt` in `api_text_differences`. The API text contains a different literal
escape; it is not decoded a second time or repaired. The complete external
manifest covers `manifest.json` too, unlike the smaller manifest published inside
the example. Both commands refuse an existing output directory.

## Capture a small existing Gist

Keep the complete expected filename, byte-count and SHA-256 map independently
from the uploaded files. For example:

```json
{
  "artifact.txt": {"bytes": 0, "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
}
```

This shows the schema only. It is not the synthetic example's manifest. Include
every published filename; a published manifest cannot supply its own expected
hash. Do not silently exempt that filename.

Separately save the existing Gist's API response and Git objects. The checker
does not perform these capture steps. For a small trusted local Gist clone:

```sh
gh api gists/GIST_ID > api.json
git --no-replace-objects --git-dir /path/to/gist.git \
  cat-file --batch-all-objects --batch > objects.batch
```

Use the default, length-framed
[`git cat-file --batch` output](https://git-scm.com/docs/git-cat-file#_batch_output),
without custom formatting, `-Z`, text conversion or filters. A larger history may
exceed the budget; a smaller capture can contain only the required commit, tree
and unique blobs. Missing objects lead to `GIT_OBJECTS_NEEDED` and their IDs, not
another publication.

Pass the independently selected full commit SHA with `--revision` and the
canonical `https://gist.github.com/OWNER/ID` with `--gist`. The saved response's
first history revision must match that pin. This checks correspondence within
the supplied capture, not remote freshness. A `raw_url` hash is not used as a
commit pin: it can identify a file blob instead.

The checker validates SHA-1 object IDs using Git's type/length/content framing,
then the commit-to-tree and filename-to-blob links. See the
[Git object description](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects).
Providing an unrelated matching blob is insufficient. Flat regular files are
supported; nested trees, symlinks and submodules are refused. Nothing is extracted
or executed.

## Interpret the result

| Exit | Decision | Meaning / next action |
| --- | --- | --- |
| 0 | `GIT_BLOBS_MATCH_MANIFEST` | Pinned Git bytes and complete API text match the manifest |
| 0 | `GIT_BLOBS_MATCH_API_TEXT_DIFFERS` | Git bytes match; retain the separate API text differences |
| 0 | `GIT_BLOBS_MATCH_API_TEXT_INCOMPLETE` | Git bytes match; API text is truncated, missing or not UTF-8 text |
| 1 | `GIT_OBJECTS_NEEDED` | Read the named existing local objects |
| 1 | `CAPTURE_MISMATCH` | Inspect filename, metadata or Git content differences |
| 2 | `INVALID_CAPTURE` or output refusal | Inspect the first framing/schema diagnostic |

The independent `git_blob_bytes_match` and `api_metadata_matches` fields retain
their separate meanings. The latter concerns the interpreted identity, revision,
filename and declared-size fields; unknown fields, including `raw_url`, are retained
without verification. An API revision mismatch is not called a proven text
representation difference. UTF-8 text is compared after exactly one JSON decode;
Unicode normalization, escape repair and newline conversion are not performed.
Truncated or absent text is never assumed to match.

Each regular input file is limited to 8 MiB, with at most 100 expected/tree files
and 1,024 captured objects. Names must be flat UTF-8 filenames, at most 255 bytes,
without control characters or path separators. Duplicate JSON keys, duplicate
objects/tree names, malformed framing, wrong object hashes and unsupported modes
are invalid. Empty blobs and shared blobs under different filenames are supported.
The output retains original inputs, helper sources and their hashes in a fresh
directory; it never resets a prior attempt.

These results check consistency of supplied bytes and hashes. They authenticate
neither GitHub nor the capture producer, establish no current remote state or
posting permission, and approve no patch. Every result has
`repost_recommended: false`. This native helper adds no Gooo execution claim.
