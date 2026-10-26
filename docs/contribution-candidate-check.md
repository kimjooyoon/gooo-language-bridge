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
merged-PR witnesses and 20 open PRs per repository, 20 issue cross-references and
3 issue comments. Open PRs include drafts and are sampled by update time.
It preserves the query, original response, API rate-limit cost, observation time,
derived Boolean observations and original Gooo receipt in a new
`evidence/candidate-scan/attempt-*/` directory for every invocation. Its
`attempt-manifest.json` hashes the source, request, response, diagnostics and
result files. No upstream
issue, PR or comment is created, and nothing is scheduled.

Each GitHub or compiler command has a deadline and records its partial output on
timeout. On POSIX systems, the collector starts the command in its own process
group and terminates that group before returning, including when the command
exits before its descendants. File-backed input/output avoids waiting for a
descendant to close a pipe. Cleanup waits at most five additional seconds for
the direct child. This covers processes that remain in the group; it is not an
isolation boundary for arbitrary programs. On other systems, cleanup covers
the direct child only.

`results.json` contains the review reason, the complete queried issue body as
`issue_body`, linked PRs and states, merge witnesses and recent comment bodies/URLs.
`repository_open_prs` retains each sampled open PR's number, URL, title, author
login, draft status, and base/head branch names and commit IDs.
`open_pr_sample_has_more` preserves whether that repository inventory is truncated.
These are untrusted source material to inspect,
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

## Body-only references need manual inspection

[Bubble Tea #1873](https://github.com/charmbracelet/bubbletea/issues/1873) exposed
an evidence-loss bug in this tool: on October 22, 2026 (Asia/Seoul), its queried
cross-reference connection was empty, while its body explicitly listed existing
PRs #1776, #1796 and #1832 and a recent comment supplied a patch. The original API
response contained the body, but the derived packet discarded it. Packets now
retain that body verbatim, including Unicode, Markdown links and code blocks.
Read `issue_body` and the comments before deciding whether to investigate a patch.

Body text remains untrusted data. A textual PR link alone does not establish
that PR's current state or coverage, so it does not set `open_pr` or `prior_pr`.
The five Boolean observations and Gooo policy are unchanged. An empty linked-PR
list and `MANUAL_TRIAGE_REQUIRED` never mean the work is available. The
[dated metadata](observations/2026-10-22-body-only-references.json) records the
observation and source/response hashes without republishing the issue or comment
bodies; it is not a copy of the original response.

## Check unlinked drafts and the intended base

An issue's cross-references can omit an active maintainer draft. During work on
[puml-as-code #6](https://github.com/yur4uwe/puml-as-code/issues/6), a PR search
returned no results, while the repository's direct open-PR list included
[draft #5](https://github.com/yur4uwe/puml-as-code/pull/5). That draft introduced
the AST used in the issue's example. Checking it avoided publishing a patch
against the wrong base. This was a search observation; the collector itself
does not use PR search.

Before starting a patch, inspect `repository_open_prs`, the issue body and linked
work. Compare relevant PRs' captured base/head revisions with the intended source
revision and read their current diff. A matching author or title alone does not
prove ownership or overlap. An unrelated open PR is not a reason to block work.
An empty search result is not a substitute for the repository inventory.
If `open_pr_sample_has_more` is true, the sample is incomplete; use a focused
follow-up to inspect omitted work before claiming there is no relevant PR.

This additional context does not set `open_pr`, which still means an issue-linked
open PR, or change any of the five Boolean observations and 32 Gooo policy cases.
Missing or malformed inventory metadata or pagination prevents a successful
packet. This includes an unavailable author login, so a deleted author's PR
requires manual follow-up rather than a successful incomplete identity packet.
Even a complete open-PR list does not establish that work is unclaimed.

## Limits and offline CI

Merged PRs are sampled by update time, then filtered by merge time. A positive
witness proves that a merge occurred; no witness does **not** prove inactivity.
It also does not establish who will review this particular change. The
`history_complete` input means only that the selected cross-reference and comment
connections have no earlier page. Repository open PRs have their own independent
`open_pr_sample_has_more` flag; neither flag covers discussions, private work,
other trackers or search results. Comments are retained, not
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

## Live collection preserves earlier evidence

A later request can fail, time out or return a different snapshot. It must not
delete the request/response or Gooo receipt used for an earlier decision. Live
collection therefore never clears its output directory. Each invocation creates
an independent attempt, including failures. A completed attempt's
`attempt-manifest.json` records its stage, actual process exit codes when known,
timeouts, observation time, error and file hashes. API, compiler and Gooo partial
stdout/stderr are retained on a timeout. An incomplete receipt never becomes a
successful result file or a test pass. There are no automatic retries.

`latest-attempt.json` is an atomically replaced pointer to the newest completed
manifest, its digest and decision. A failed newest attempt remains visibly
failed; it does not silently select an earlier success. Previous attempt bytes
are retained, including the previous successful manifest. Legacy root files,
including an old `summary.json`, are left untouched: they are historical data,
not the new latest result. Read the pointer or the manifest path printed by the
current invocation. A process killed before finalization may leave an incomplete
attempt; the last completed pointer does not prove that interrupted run passed.

Each live attempt also captures the collector and the three policy source files.
`source_snapshots` maps original repository paths to these copies; their hashes
match on a successful collection; a change during collection fails closed.
Retained source copies allow later inspection without
assuming the working tree still has the same bytes. A compiler binary is hashed,
not copied. This records supplied data and executed process observations; it
does not independently authenticate GitHub content, establish maintainer demand
or authorize a post.

At most eight live attempt paths are allowed in a collection directory, including
unfinished attempts. On exhaustion, the tool performs no new GitHub request and
does not change old data or the pointer. Preserve that directory and use a fresh
checkout for further collection. Use one invocation at a time per directory;
concurrent collectors and an unbounded archival service are outside this tool's
scope. The existing 32-case offline CI snapshot stays separate in
`evidence/candidate-policy/`; it makes no GitHub request and is still regenerated
for the current bounded verification. No live evidence or private mail is added
to the repository.

For a separate role/evidence-bound decision about whether a response adds useful
information, see [response planning](contribution-response-planning.md). Its B1
fixtures and producer evidence contract preserve unknowns and have no publishing
effect. They do not change these five observations or 32 candidate-policy cases.
