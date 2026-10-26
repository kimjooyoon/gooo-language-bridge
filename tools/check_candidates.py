"""Read-only, bounded candidate packets. A review reason is never approval."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
from itertools import product
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'bridges/contribution-review'
KEY = 'bridge/contribution:Review'
ACTIVITY = 'urn:gooo:contribution:review'
FIELDS = ('issue_open', 'open_pr', 'prior_pr', 'history_complete', 'recent_merge')
MAX_LIVE_ATTEMPTS = 8


def review(row):
    if set(row) != set(FIELDS) or any(type(v) is not bool for v in row.values()):
        raise ValueError('observations must contain exactly five Boolean fields')
    if not row['issue_open']:
        return 'ISSUE_CLOSED'
    if row['open_pr']:
        return 'REVIEW_OPEN_PR'
    if row['prior_pr']:
        return 'REVIEW_PRIOR_PR'
    if not row['history_complete']:
        return 'REVIEW_TRUNCATED_HISTORY'
    if not row['recent_merge']:
        return 'CHECK_MAINTENANCE_ACTIVITY'
    return 'MANUAL_TRIAGE_REQUIRED'


def parse_candidates(candidates):
    if not 1 <= len(candidates) <= 8 or len(set(c.lower() for c in candidates)) != len(candidates):
        raise ValueError('provide 1..8 distinct owner/repo#issue candidates')
    result = []
    for candidate in candidates:
        match = re.fullmatch(r'([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9_.-]+)#([1-9][0-9]*)', candidate)
        if not match:
            raise ValueError('invalid candidate: ' + candidate)
        owner, name, number = match.groups()
        result.append((owner, name, int(number)))
    return result


def request(candidates):
    parsed = parse_candidates(candidates)
    definitions, variables, repos = [], {}, []
    grouped = {}
    for i, (owner, name, number) in enumerate(parsed):
        grouped.setdefault((owner.lower(), name.lower()), []).append((i, number))
    for r, ((owner, name), issues) in enumerate(grouped.items()):
        definitions += ['$owner%d:String!' % r, '$name%d:String!' % r]
        variables.update({'owner%d' % r: owner, 'name%d' % r: name})
        block = '''r%d:repository(owner:$owner%d,name:$name%d) {
 nameWithOwner isPrivate
 pullRequests(first:20,states:MERGED,orderBy:{field:UPDATED_AT,direction:DESC}) {
  nodes { number url mergedAt } pageInfo { hasNextPage }
 }
 openPullRequests:pullRequests(first:20,states:OPEN,orderBy:{field:UPDATED_AT,direction:DESC}) {
  nodes { number url title author { login } isDraft baseRefName baseRefOid headRefName headRefOid }
  pageInfo { hasNextPage }
 }
''' % (r, r, r)
        for i, number in issues:
            definitions.append('$issue%d:Int!' % i)
            variables['issue%d' % i] = number
            block += '''i%d:issue(number:$issue%d) {
  number url state title body
  comments(last:3) { nodes { url body author { login } } pageInfo { hasPreviousPage } }
  timelineItems(last:20,itemTypes:[CROSS_REFERENCED_EVENT]) {
   nodes { ... on CrossReferencedEvent { source { __typename ... on PullRequest {
    number url state title mergedAt
   } } } } pageInfo { hasPreviousPage }
  }
 }
''' % (i, i)
        repos.append(block + '}')
    return {'query': 'query(' + ','.join(definitions) + '){rateLimit { cost remaining resetAt }' + '\n'.join(repos) + '}',
            'variables': variables}


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamp lacks timezone')
    return result


def page(connection, direction):
    if not isinstance(connection['nodes'], list) or type(connection['pageInfo'][direction]) is not bool:
        raise ValueError('invalid pagination evidence')
    return connection['pageInfo'][direction]


def check_pr_identity(row):
    if (type(row['number']) is not int or row['number'] < 1
            or not re.fullmatch(r'https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/'
                                + str(row['number']), row['url'])):
        raise ValueError('invalid pull request identity')


def open_pr_inventory(repository):
    connection = repository['openPullRequests']
    has_more = page(connection, 'hasNextPage')
    rows = connection['nodes']
    if len(rows) > 20:
        raise ValueError('open pull request sample exceeds query bound')
    seen = set()
    for pr in rows:
        check_pr_identity(pr)
        expected = 'https://github.com/%s/pull/%d' % (repository['nameWithOwner'], pr['number'])
        if pr['url'].lower() != expected.lower() or pr['number'] in seen:
            raise ValueError('open pull request repository or identity mismatch')
        seen.add(pr['number'])
        if (not isinstance(pr['title'], str) or not pr['title'].strip()
                or type(pr['isDraft']) is not bool
                or not isinstance(pr['author'], dict)
                or not isinstance(pr['author'].get('login'), str)
                or not pr['author']['login'].strip()):
            raise ValueError('invalid open pull request metadata')
        for field in ('baseRefName', 'headRefName'):
            if not isinstance(pr[field], str) or not pr[field].strip():
                raise ValueError('invalid open pull request ref name')
        for field in ('baseRefOid', 'headRefOid'):
            if not isinstance(pr[field], str) or not re.fullmatch(r'[0-9a-fA-F]{40}', pr[field]):
                raise ValueError('invalid open pull request revision')
    return rows, has_more


def packets(response, candidates, now):
    if response.get('errors') or not isinstance(response.get('data'), dict):
        raise ValueError('GitHub response is partial or failed')
    result = []
    repo_indexes = {}
    for owner, name, _ in parse_candidates(candidates):
        repo_indexes.setdefault((owner.lower(), name.lower()), len(repo_indexes))
    for i, candidate in enumerate(candidates):
        repo, number = candidate.rsplit('#', 1)
        repository = response['data']['r%d' % repo_indexes[tuple(repo.lower().split('/'))]]
        if repository['isPrivate'] is not False:
            raise ValueError('only public repository evidence is supported')
        if repository['nameWithOwner'].lower() != repo.lower():
            raise ValueError('repository identity mismatch')
        open_prs, open_pr_sample_has_more = open_pr_inventory(repository)
        issue = repository['i%d' % i]
        if type(issue['number']) is not int or issue['number'] != int(number) or issue['url'].lower() != ('https://github.com/' + repo + '/issues/' + number).lower():
            raise ValueError('issue identity mismatch')
        if not isinstance(issue['body'], str):
            raise ValueError('issue body must be text')
        if issue['state'] not in ('OPEN', 'CLOSED'):
            raise ValueError('unknown issue state')
        merged = repository['pullRequests']
        merge_page_incomplete = page(merged, 'hasNextPage')
        witnesses = []
        for pr in merged['nodes']:
            check_pr_identity(pr)
            when = timestamp(pr['mergedAt'])
            if when > now:
                raise ValueError('future merge timestamp')
            if when >= now - timedelta(days=30):
                witnesses.append(pr)
        timeline, comments = issue['timelineItems'], issue['comments']
        history_incomplete = page(timeline, 'hasPreviousPage') | page(comments, 'hasPreviousPage')
        references = []
        for event in timeline['nodes']:
            source = event['source']
            if source['__typename'] not in ('Issue', 'PullRequest'):
                raise ValueError('unknown cross-reference source')
            if source['__typename'] == 'PullRequest':
                check_pr_identity(source)
                if source['state'] not in ('OPEN', 'CLOSED', 'MERGED'):
                    raise ValueError('unknown referenced PR state')
                references.append(source)
        observation = {
            'issue_open': issue['state'] == 'OPEN',
            'open_pr': any(p['state'] == 'OPEN' for p in references),
            'prior_pr': any(p['state'] in ('CLOSED', 'MERGED') for p in references),
            'history_complete': not history_incomplete,
            'recent_merge': bool(witnesses),
        }
        result.append({'candidate': candidate, 'url': issue['url'], 'title': issue['title'],
                       'issue_body': issue['body'],
                       'observation': observation, 'expected_review_reason': review(observation),
                       'recent_merge_witnesses': witnesses, 'linked_prs': references,
                       'repository_open_prs': open_prs,
                       'open_pr_sample_has_more': open_pr_sample_has_more,
                       'recent_comments': comments['nodes'],
                       'merge_sample_has_more': merge_page_incomplete})
    return result


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def verify_receipt(receipt, rows, code):
    runtime = receipt.get('result', {}).get('runtime', {})
    if (type(code) is not int or code != 0 or receipt.get('decision') != 'PASS'
            or any(type(runtime.get(k)) is not int or runtime[k] != len(rows)
                   for k in ('finite_passed', 'finite_total'))):
        raise ValueError('missing complete Gooo policy PASS')
    traces = {}
    for trace in runtime['traces']:
        index = trace['case_index']
        if type(index) is not int or index in traces:
            raise ValueError('invalid Gooo case index')
        traces[index] = trace
    if set(traces) != set(range(len(rows))):
        raise ValueError('Gooo case domain differs')
    for i, row in enumerate(rows):
        deliveries = traces[i]['deliveries']
        if len(deliveries) != 1:
            raise ValueError('ambiguous Gooo policy delivery')
        d = deliveries[0]
        expected = review(row['observation'])
        if (d['activity_id'] != ACTIVITY or d['input'] != row['observation']
                or d['actual'] != expected or d['expected'] != expected or d['passed'] is not True):
            raise ValueError('Gooo policy input, identity or result differs')
        if any(type(v) is not bool for v in d['input'].values()):
            raise ValueError('Gooo input lost Boolean types')
        row['review_reason'] = d['actual']


def _run_bounded(command, *, timeout, input=None, **kwargs):
    """Retain bytes and stop the owned POSIX process group before returning."""
    with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout, \
            tempfile.TemporaryFile() as stderr:
        if input is not None:
            stdin.write(input)
        stdin.seek(0)
        process = subprocess.Popen(command, stdin=stdin, stdout=stdout, stderr=stderr,
                                   start_new_session=os.name == 'posix', **kwargs)
        timeout_error = None
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            timeout_error = error
        finally:
            # A completed leader can still have descendants holding the output files.
            if os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired as error:
                if timeout_error is None:
                    timeout_error = error
                timeout_error.cleanup_timed_out = True
        stdout.seek(0)
        stderr.seek(0)
        output, diagnostics = stdout.read(), stderr.read()
        if timeout_error is not None:
            timeout_error.output = output
            timeout_error.stderr = diagnostics
            raise timeout_error
        return subprocess.CompletedProcess(command, process.returncode, output, diagnostics)


def captured_run(command, out, stdout_name, stderr_name, summary, stage, **kwargs):
    """Keep original process output, including bytes produced before a timeout."""
    summary['stage'] = stage
    try:
        process = _run_bounded(command, **kwargs)
    except subprocess.TimeoutExpired as error:
        (out / stdout_name).write_bytes(error.output or b'')
        (out / stderr_name).write_bytes(error.stderr or b'')
        summary[stage + '_timed_out'] = True
        if getattr(error, 'cleanup_timed_out', False):
            summary[stage + '_cleanup_timed_out'] = True
        raise
    (out / stdout_name).write_bytes(process.stdout)
    (out / stderr_name).write_bytes(process.stderr)
    summary[stage + '_exit_code'] = process.returncode
    return process


def latest_pointer(root, attempt, manifest):
    """Publish only a completed manifest; never replace an earlier attempt."""
    value = {'schema': 'gooo-language-bridge/candidate-attempt-pointer/v1',
             'attempt_manifest': manifest.relative_to(root).as_posix(),
             'manifest_sha256': digest(manifest), 'decision': attempt['decision']}
    fd, name = tempfile.mkstemp(prefix='.latest-', suffix='.tmp', dir=root)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(json.dumps(value, indent=2) + '\n')
        os.replace(name, root / 'latest-attempt.json')
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', action='append', default=[], metavar='OWNER/REPO#N')
    parser.add_argument('--self-test', action='store_true', help='32 offline policy cases, no GitHub request')
    parser.add_argument('--gooo', required=True)
    args = parser.parse_args(argv)
    if args.self_test == bool(args.candidate):
        parser.error('choose either --self-test or --candidate')
    now = datetime.now(timezone.utc)
    output_root = ROOT / 'evidence' / ('candidate-policy' if args.self_test else 'candidate-scan')
    output_root.mkdir(parents=True, exist_ok=True)
    if args.self_test:
        # The offline CI fixture remains a single fresh snapshot, separate from live history.
        out = output_root
        for p in out.iterdir():
            if p.is_file():
                p.unlink()
    else:
        if len(list(output_root.glob('attempt-*'))) >= MAX_LIVE_ATTEMPTS:
            print(json.dumps({'schema': 'gooo-language-bridge/candidate-review/v1',
                              'decision': 'FAIL_CLOSED', 'mode': 'live', 'github_requests': 0,
                              'error': 'retained attempt budget reached; preserve this directory and use a fresh checkout'}))
            return 1
        out = Path(tempfile.mkdtemp(prefix='attempt-', dir=output_root))
    started = time.monotonic()
    summary = {'schema': 'gooo-language-bridge/candidate-review/v1', 'decision': 'FAIL_CLOSED',
               'observed_at': now.isoformat(), 'mode': 'offline' if args.self_test else 'live',
               'github_requests': 0, 'stage': 'capture',
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID')}
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')
    binary = str(Path(args.gooo).resolve())
    try:
        if not args.self_test:
            summary['attempt'] = out.relative_to(ROOT).as_posix()
            summary['source_snapshots'] = {}
            for source, name in [(ROOT / 'tools/check_candidates.py', 'collector-source.py'),
                                 (BRIDGE / 'main.gooo', 'policy-source.gooo'),
                                 (BRIDGE / 'gooo.workspace.json', 'workspace-source.json'),
                                 (BRIDGE / 'provenance.json', 'policy-provenance.json')]:
                (out / name).write_bytes(source.read_bytes())
                summary['source_snapshots'][source.relative_to(ROOT).as_posix()] = (out / name).relative_to(ROOT).as_posix()
        summary['stage'] = 'input'
        if args.self_test:
            rows = [{'observation': dict(zip(FIELDS, values))} for values in product((False, True), repeat=5)]
        else:
            payload = json.dumps(request(args.candidate)).encode()
            (out / 'request.json').write_bytes(payload)
            summary['github_requests'] = 1
            api = captured_run(['gh', 'api', 'graphql', '--input', '-'], out,
                               'github.json', 'github.stderr', summary, 'api', input=payload, timeout=60)
            if api.returncode:
                raise ValueError('GitHub API request failed; inspect github.stderr')
            response = json.loads(api.stdout)
            rows = packets(response, args.candidate, now)
            summary['github_rate_limit'] = response['data']['rateLimit']
        (out / 'observations.json').write_text(json.dumps(rows, indent=2) + '\n')
        cases_path = out / 'cases.json'
        cases_path.write_text(json.dumps({'schema': 'gooo/body-composition-cases/v1', 'cases': [
            {'inputs': {KEY: r['observation']}, 'expected': {KEY: review(r['observation'])}} for r in rows]}, indent=2) + '\n')
        version = captured_run([binary, 'version', '--build', '--json'], out,
                               'compiler.json', 'compiler.stderr', summary, 'compiler', timeout=10)
        if version.returncode or json.loads(version.stdout).get('version') != '0.6.38-dev':
            raise ValueError('compiler version mismatch')
        executed = captured_run([binary, 'package', 'execute', '--json', '--cases', str(cases_path),
                                 'gooo.workspace.json'], out, 'execution.json', 'execution.stderr',
                                summary, 'execution', cwd=BRIDGE, env=env, timeout=90)
        receipt = json.loads(executed.stdout)
        if (receipt['cases_digest'] != digest(cases_path)
                or receipt['manifest_digest'] != digest(BRIDGE / 'gooo.workspace.json')):
            raise ValueError('receipt input digest differs')
        verify_receipt(receipt, rows, executed.returncode)
        if not args.self_test and any((ROOT / source).read_bytes() != (ROOT / snapshot).read_bytes()
                                      for source, snapshot in summary['source_snapshots'].items()):
            raise ValueError('source changed during collection; inspect captured source snapshots')
        (out / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
        summary.update(decision='PASS', cases=len(rows), github_requests=0 if args.self_test else 1,
                       stage='complete', compiler_sha256=digest(Path(binary)),
                       reasons=[r['review_reason'] for r in rows])
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        paths = list(out.iterdir()) + list(BRIDGE.iterdir()) + [ROOT / 'tools/check_candidates.py']
        summary['sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)
                             if p.is_file() and p.name != 'summary.json'}
        manifest = out / ('summary.json' if args.self_test else 'attempt-manifest.json')
        manifest.write_text(json.dumps(summary, indent=2) + '\n')
        if not args.self_test:
            latest_pointer(output_root, summary, manifest)
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
