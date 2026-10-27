# Check a saved review without repeating publication

A review POST can succeed even if a later confirmation script fails. Some saved
review-comment collections expose diff `position` without `line` or `side`.
Those fields are different: guessing a source line from a diff offset can
confirm the wrong anchor, and a failed check is not evidence that posting failed.

The Python standard-library helper compares the original submitted request with
saved review/comment JSON. It reports missing evidence or mismatches and retains
original bytes in a fresh output directory. It performs no network requests,
GitHub writes, source execution or approval.

## Try the synthetic API-shaped example

The included IDs, commit, URL and timestamps are **synthetic**. These files are
not captures of a real GitHub review. From the repository root:

```sh
python3 tools/check_review_readback.py \
  --pull-request https://github.com/example/project/pull/12 \
  --reviewer reviewer \
  --request examples/review-readback/request.json \
  --review examples/review-readback/review.json \
  --comments examples/review-readback/comments.json \
  --out /tmp/review-readback-missing
```

Expect exit 1, `COMMENT_DETAILS_NEEDED`, and `missing_comment_ids: [50]`.
The saved collection has position 19, but no source-line evidence. With its
separately saved detail response:

```sh
python3 tools/check_review_readback.py \
  --pull-request https://github.com/example/project/pull/12 \
  --reviewer reviewer \
  --request examples/review-readback/request.json \
  --review examples/review-readback/review.json \
  --comments examples/review-readback/comments.json \
  --details examples/review-readback/details.json \
  --out /tmp/review-readback-complete
```

Expect exit 0 and `CAPTURED_REVIEW_MATCHES_REQUEST`, with source line 7. Choose new
output paths for each attempt; an existing directory is refused and never reset.
No Go or Gooo compiler, account token or repository checkout is needed to process
saved files. When calling the script from another directory, use absolute paths.

## Continue from an existing review ID

Keep the exact submitted body as `request.json`, including its explicit
`commit_id`, `event`, body and requested comments. Capture the existing review
with a GET, and its comment collection as one flat JSON array:

```sh
gh api repos/OWNER/REPO/pulls/NUMBER/reviews/REVIEW_ID > review.json
gh api 'repos/OWNER/REPO/pulls/NUMBER/reviews/REVIEW_ID/comments?per_page=100' > comments.json
```

For each missing ID, save the
[individual comment GET](https://docs.github.com/en/rest/pulls/comments#get-a-review-comment-for-a-pull-request)
and combine the replies into a flat array for `--details`. For a single ID:

```sh
gh api repos/OWNER/REPO/pulls/comments/COMMENT_ID --jq '[.]' > details.json
```

The checker also accepts a fully populated collection without separate details.
For a paginated collection, capture every page into one flat array. This helper
checks the supplied array's count against the request; it cannot establish that
the remote collection is current or complete. Always continue by reading the
existing review/comment IDs. Every result has `repost_recommended: false`.

The target is the exact canonical HTTPS PR URL, including owner/repository case.
The optional `--reviewer` declares the expected login. The review and comments
must carry that author; usernames are compared exactly. Comment replies do not
satisfy newly submitted inline comments. COMMENT, APPROVE and REQUEST_CHANGES
request events are supported as captured metadata, including body-only reviews.
Legacy position-only request payloads are refused; line/side requests and ranges
are supported.

A later current head or shifted line does not erase a bound original comment:
when supplied, `original_commit_id`, `original_line` and range metadata are used.
Without original metadata, current line/range evidence is usable only at the exact
requested commit. Missing anchor/range fields ask for detail evidence. Conflicting
bodies, PRs, authors, review IDs, original commits, lines or sides remain explicit
mismatches. Duplicate IDs and malformed JSON are invalid captures. Unknown API
response fields are retained without being interpreted.

## Interpret the result

| Exit | Decision | Next action |
| --- | --- | --- |
| 0 | `CAPTURED_REVIEW_MATCHES_REQUEST` | Retain the captured correspondence |
| 1 | `COMMENT_DETAILS_NEEDED` | Read the named existing comments |
| 1 | `REVIEW_DETAILS_NEEDED` | Read the existing review |
| 1 | `CAPTURE_MISMATCH` | Inspect the request/capture difference |
| 2 | `INVALID_CAPTURE` or output refusal | Inspect the first diagnostic |

Inputs are bounded to 8 MiB per regular file and 100 requested/listed/detail
comments. Duplicate JSON object keys, non-finite constants, invalid identities
and unsupported request fields are refused. The output preserves supplied input
bytes, hashes and the three Python source files used by this native helper.
Invalid captures retain the diagnostic and whatever input had already been read.

A match concerns these supplied bytes only. It authenticates neither GitHub nor
the producer, establishes no remote freshness, and verifies no patch approval or
posting permission. A captured APPROVED state is metadata, not a new approval
from this checker. This workflow adds no native Gooo execution or adoption claim.
