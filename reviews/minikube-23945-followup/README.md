# minikube #23945: preserve the default workflow shell

The [maintainer review](https://github.com/kubernetes/minikube/pull/23945#pullrequestreview-5657821902)
asked why two workflow steps changed their shell and requested a narrower change.
Commit [`4331e26157df2b298af011c1e922f2c04c80f512`](https://github.com/kimjooyoon/minikube/commit/4331e26157df2b298af011c1e922f2c04c80f512)
removes those shell overrides and scopes `pipefail` to each download pipeline.
The default `bash -e` behavior handles failures elsewhere in the step.
The two comments concern
[Rootless Docker](https://github.com/kubernetes/minikube/pull/23945#discussion_r4381559133)
and [vfkit/vmnet-helper](https://github.com/kubernetes/minikube/pull/23945#discussion_r4381566061).

## Observed result

The unchanged captured verifier extracts the **complete actual run block** from
each workflow and executes it with `/bin/bash -e`. Real curl requests go only to
a loopback HTTP fixture. Package-manager, installer, sudo and Docker operations
are inert logged fixtures, included with the case captures.

| Source | Normal/error-propagation controls | HTTP 404/500 behavior |
| --- | --- | --- |
| Original base `34f70057d29a36eae8b8bec815b33ba1599ff80f` | 6 pass | 4 failures reproduced |
| Revised workflow bytes at `4331e26157df2b298af011c1e922f2c04c80f512` | 6 pass | 4 pass |

The six controls are HTTP 200, failure of the earlier apt-get/brew operation before
any HTTP request, and receiver failure, for both steps. All **10 revised cases
pass**; the original source has 6 passes and 4 failures. The run took 12.999
seconds. Both complete workflow file hashes were unchanged during execution and
were then bound to the committed head in `tested-source.json`.

`workflow-syntax.json` records successful Bash syntax checks for all 18 run blocks
in the two changed workflows. `validation/report.json` retains exact source/run
blocks, case results and capture hashes. Each case includes its input script,
stdout, stderr, request/operation logs and generated inert command fixtures.
The entire `validation/` tree is copied byte-for-byte from the completed run;
absolute paths and ephemeral loopback ports remain historical metadata.

The [prior 31-case matrix](https://github.com/kimjooyoon/gooo-language-bridge/tree/94b44d2fc9c8f1774e2b937bf8dcbefa6af160c2/reviews/minikube-23944)
belongs to the previous PR head. It was not rerun for this follow-up. This new
execution covers the two revised workflow steps; the other 24 changed files are
recorded unchanged from that previous head. This package does not establish a
hosted Actions pass, full minikube integration success, CLA authorization or
maintainer acceptance. No installer, Kubernetes cluster or external download ran.

## Reproduce this bounded scope

Use a trusted minikube checkout at the exact head above with the two original
base workflow blobs already present. The wrapper checks the head and revised
workflow hashes, disables Git lazy fetching, and refuses an existing output
directory:

```sh
python3 run.py --source /absolute/path/to/minikube --output /new/output/directory
```

Requires Python 3, Git, `/bin/bash` and `/usr/bin/curl`. The captured fixture's curl
adapter also uses `/usr/bin/python3`. The recorded run used macOS Bash 3.2.57 and
curl 8.7.1; it emulates the documented Actions default shell locally. Each child
process group is closed after the case, with an 8-second deadline and 8 MiB
stdout/stderr limits. `run.py` was packaged after the recorded execution; only
its help and Python compilation were checked, without repeating the experiment.

`file-integrity.json` hashes every other file in this package. These hashes bind
the captured bytes and do not authenticate authorship. Captured minikube source
is covered by `LICENSE.upstream` (Apache 2.0).
