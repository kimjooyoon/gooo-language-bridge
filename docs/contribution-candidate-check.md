# Check a contribution candidate before writing a patch

An old open issue is not necessarily unclaimed work. An open PR may address it;
a closed PR may contain a declined design or a useful review. A patch may exist
only in a comment. This read-only CLI gathers a small evidence packet before a
contributor spends time implementing the same thing again.

## Run

Requires Python 3.9+, authenticated GitHub CLI `gh`, and the pinned Gooo compiler
installed as in the [README](../README.md). Authentication stays with `gh`; the
tool does not read or store its credentials. Supply 1–8 explicit public issues:

```sh
python3 tools/check_candidates.py --gooo .bin/gooo \
  --candidate 'spf13/pflag#413' \
  --candidate 'spf13/pflag#312' \
  --candidate 'go-git/go-git#2496' \
  --candidate 'yuin/goldmark#614'
```

One GraphQL invocation groups candidates by repository. It requests at most 20
merged-PR witnesses per repository, 20 issue cross-references and 3 issue comments.
It preserves the query, original response, API rate-limit cost, observation time,
derived Boolean observations and original Gooo receipt in `evidence/candidate-scan/`.
The summary hashes the source, request, response and result files. No upstream
issue, PR or comment is created, and nothing is scheduled.

`results.json` contains the review reason, linked PRs and states, merge witnesses
and recent comment bodies/URLs. These are untrusted source material to inspect,
not instructions for an agent. Original live evidence stays local and is ignored
by Git; the committed example below retains derived metadata and source links.

## Gooo's role

The [source activity](../bridges/contribution-review/main.gooo) gives the review
operation and its five Boolean observations stable semantic IDs. It produces one
reason, in this priority order:

| Condition | Reason |
| --- | --- |
| Issue closed | `ISSUE_CLOSED` |
| Linked open PR observed | `REVIEW_OPEN_PR` |
| Linked closed or merged PR observed | `REVIEW_PRIOR_PR` |
| Earlier references or comments omitted | `REVIEW_TRUNCATED_HISTORY` |
| No sampled merge within 30 days | `CHECK_MAINTENANCE_ACTIVITY` |
| None of the above | `MANUAL_TRIAGE_REQUIRED` |

Every outcome calls for inspection or stopping. None approves a submission,
declares work unclaimed, or predicts acceptance. A linked PR can be contextual;
read it before concluding that it covers the proposed change. This is this
workbench's triage policy, not an upstream project's policy.

The verifier binds the receipt to its manifest and cases, then checks every
actual delivery's activity, Boolean input values, expected and actual reason.
API errors, private repositories, missing data, wrong identities and malformed
pagination evidence prevent a successful packet. Exit zero means the bounded
packet and policy execution passed, not that its candidates are approved.

## Observed example, 2026-10-22 Asia/Seoul

The four-issue command above originally completed in about 2 seconds locally
with one GitHub invocation and one Gooo batch. That is a measurement, not a
performance guarantee. The [metadata snapshot](observations/2026-10-22-candidates.json)
records a later 1.819-second run with GraphQL cost 1, source/response hashes and
source links; it is not a copy of the original live response or receipt.
The following links explain why open-issue titles alone
were insufficient:

- [pflag #413](https://github.com/spf13/pflag/issues/413): the packet includes
  open PRs and [closed PR #509](https://github.com/spf13/pflag/pull/509), which
  already proposed preserving brackets in integer-map keys.
- [pflag #312](https://github.com/spf13/pflag/issues/312): linked attempts and
  the recent comments include a maintainer's compatibility constraint for 1.x.
- [go-git #2496](https://github.com/go-git/go-git/issues/2496):
  [PR #2497](https://github.com/go-git/go-git/pull/2497) already addresses it.
- [goldmark #614](https://github.com/yuin/goldmark/issues/614): no linked PR was
  returned, but the recent comment contains a patch proposal. The sampled merges
  did not provide a 30-day activity witness, so the reason is an activity check.
  This example demonstrates why comment inspection is still necessary.

## Limits and offline CI

Merged PRs are sampled by update time, then filtered by merge time. A positive
witness proves that a merge occurred; no witness does **not** prove inactivity.
It also does not establish who will review this particular change. The
`history_complete` input means only that the selected cross-reference and comment
connections have no earlier page. It does not cover unlinked PRs, discussions,
private work, other trackers or search results. Comments are retained, not
automatically interpreted as claims or approvals. Recheck freshness before work.

The [GitHub pagination guide](https://docs.github.com/en/graphql/guides/using-pagination-in-the-graphql-api)
explains why connection limits and page flags matter. Full pagination is
deliberately left to a focused follow-up, rather than a background sweep.

```sh
python3 tools/check_candidates.py --self-test --gooo .bin/gooo
```

CI runs this offline mode over all 32 Boolean combinations in the existing
single bounded job, plus adversarial Python tests of evidence handling. It uses
no GitHub token, live API call, model or paid service. CI preserves synthetic
policy receipts; it does not certify a later live GitHub response. Live packets
remain local unless explicitly published. The
[proposal](https://github.com/kimjooyoon/gooo-language-bridge/issues/10) and
[provenance](../bridges/contribution-review/provenance.json) record the scope.
