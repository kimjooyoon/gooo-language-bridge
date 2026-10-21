"""Read-only, bounded candidate packets. A review reason is never approval."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
from itertools import product
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'bridges/contribution-review'
KEY = 'bridge/contribution:Review'
ACTIVITY = 'urn:gooo:contribution:review'
FIELDS = ('issue_open', 'open_pr', 'prior_pr', 'history_complete', 'recent_merge')


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', action='append', default=[], metavar='OWNER/REPO#N')
    parser.add_argument('--self-test', action='store_true', help='32 offline policy cases, no GitHub request')
    parser.add_argument('--gooo', required=True)
    args = parser.parse_args()
    if args.self_test == bool(args.candidate):
        parser.error('choose either --self-test or --candidate')
    now = datetime.now(timezone.utc)
    out = ROOT / 'evidence' / ('candidate-policy' if args.self_test else 'candidate-scan')
    out.mkdir(parents=True, exist_ok=True)
    for p in out.iterdir():
        if p.is_file():
            p.unlink()
    started = time.monotonic()
    summary = {'schema': 'gooo-language-bridge/candidate-review/v1', 'decision': 'FAIL_CLOSED',
               'observed_at': now.isoformat(), 'mode': 'offline' if args.self_test else 'live',
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID')}
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')
    binary = str(Path(args.gooo).resolve())
    try:
        if args.self_test:
            rows = [{'observation': dict(zip(FIELDS, values))} for values in product((False, True), repeat=5)]
        else:
            payload = json.dumps(request(args.candidate)).encode()
            (out / 'request.json').write_bytes(payload)
            api = subprocess.run(['gh', 'api', 'graphql', '--input', '-'], input=payload,
                                 capture_output=True, timeout=60)
            (out / 'github.json').write_bytes(api.stdout)
            (out / 'github.stderr').write_bytes(api.stderr)
            summary['api_exit_code'] = api.returncode
            if api.returncode:
                raise ValueError('GitHub API request failed; inspect github.stderr')
            response = json.loads(api.stdout)
            rows = packets(response, args.candidate, now)
            summary['github_rate_limit'] = response['data']['rateLimit']
        (out / 'observations.json').write_text(json.dumps(rows, indent=2) + '\n')
        cases_path = out / 'cases.json'
        cases_path.write_text(json.dumps({'schema': 'gooo/body-composition-cases/v1', 'cases': [
            {'inputs': {KEY: r['observation']}, 'expected': {KEY: review(r['observation'])}} for r in rows]}, indent=2) + '\n')
        version = subprocess.run([binary, 'version', '--build', '--json'], capture_output=True, timeout=10)
        (out / 'compiler.json').write_bytes(version.stdout)
        if version.returncode or json.loads(version.stdout).get('version') != '0.6.38-dev':
            raise ValueError('compiler version mismatch')
        executed = subprocess.run([binary, 'package', 'execute', '--json', '--cases', str(cases_path),
                                   'gooo.workspace.json'], cwd=BRIDGE, env=env, capture_output=True, timeout=90)
        (out / 'execution.json').write_bytes(executed.stdout)
        (out / 'execution.stderr').write_bytes(executed.stderr)
        summary['execution_exit_code'] = executed.returncode
        receipt = json.loads(executed.stdout)
        if (receipt['cases_digest'] != digest(cases_path)
                or receipt['manifest_digest'] != digest(BRIDGE / 'gooo.workspace.json')):
            raise ValueError('receipt input digest differs')
        verify_receipt(receipt, rows, executed.returncode)
        (out / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
        summary.update(decision='PASS', cases=len(rows), github_requests=0 if args.self_test else 1,
                       compiler_sha256=digest(Path(binary)), reasons=[r['review_reason'] for r in rows])
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        paths = list(out.iterdir()) + list(BRIDGE.iterdir()) + [Path(__file__)]
        summary['sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)
                             if p.is_file() and p.name != 'summary.json'}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
