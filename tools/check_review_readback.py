"""Check captured GitHub review replies against a request; never fetch or publish."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

if __package__:
    from .compare_go_tests import capture, decode
else:
    from compare_go_tests import capture, decode

STATES = {'COMMENT': 'COMMENTED', 'APPROVE': 'APPROVED',
          'REQUEST_CHANGES': 'CHANGES_REQUESTED'}
SHA = re.compile(r'[0-9a-f]{40}')
MAX_COMMENTS = 100


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, empty=False):
    require(type(value) is str and (empty or bool(value)), 'expected text')
    value.encode('utf-8', errors='strict')
    return value


def positive(value):
    require(type(value) is int and value > 0, 'expected positive integer ID/line')
    return value


def pull_request_url(value):
    parsed = urlsplit(text(value))
    require(parsed.scheme == 'https' and bool(parsed.hostname)
            and not parsed.username and not parsed.password
            and not parsed.query and not parsed.fragment
            and re.fullmatch(r'/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[1-9][0-9]*', parsed.path)
            and value == parsed.geturl(), 'expected canonical HTTPS pull request URL')
    return value


def api_pull_request(target):
    parsed = urlsplit(target)
    owner, repo, _, number = parsed.path.strip('/').split('/')
    base = ('https://api.github.com' if parsed.hostname == 'github.com'
            else 'https://' + parsed.netloc + '/api/v3')
    return base + '/repos/' + owner + '/' + repo + '/pulls/' + number


def fingerprint(comment):
    return (comment['path'], comment['body'], comment['line'], comment['side'],
            comment.get('start_line'), comment.get('start_side'))


def request_comments(request):
    require(type(request) is dict and {'commit_id', 'event', 'body'} <= set(request)
            and set(request) <= {'commit_id', 'event', 'body', 'comments'},
            'expected pinned review request with body/event and line-based comments')
    require(type(request['commit_id']) is str and SHA.fullmatch(request['commit_id']),
            'expected full lowercase commit SHA')
    require(type(request['event']) is str and request['event'] in STATES,
            'unsupported submitted review event')
    text(request['body'], empty=True)
    rows = request.get('comments', [])
    require(type(rows) is list and len(rows) <= MAX_COMMENTS, 'review comment budget')
    for row in rows:
        require(type(row) is dict and {'path', 'body', 'line', 'side'} <= set(row)
                and set(row) <= {'path', 'body', 'line', 'side', 'start_line', 'start_side'},
                'unsupported comment request; position-only requests need inspection')
        text(row['path'])
        text(row['body'])
        positive(row['line'])
        require(row['side'] in ('LEFT', 'RIGHT'), 'invalid comment side')
        require(('start_line' in row) == ('start_side' in row), 'incomplete range request')
        if 'start_line' in row:
            positive(row['start_line'])
            require(row['start_side'] in ('LEFT', 'RIGHT'), 'invalid range side')
    return rows


def collection(value):
    require(type(value) is list and len(value) <= MAX_COMMENTS, 'expected bounded comment array')
    result = {}
    for row in value:
        require(type(row) is dict, 'expected comment object')
        identity = positive(row.get('id'))
        require(identity not in result, 'duplicate captured comment ID')
        result[identity] = row
    return result


def login(row):
    user = row.get('user')
    require(type(user) is dict, 'missing captured author')
    return text(user.get('login'))


def check(request, review, comments, details, target, reviewer=None):
    target = pull_request_url(target)
    expected_rows = request_comments(request)
    expected = Counter(fingerprint(row) for row in expected_rows)
    require(type(review) is dict, 'expected review object')
    review_id = positive(review.get('id'))
    author = login(review)
    listed, details = collection(comments), collection(details)
    issues, missing, matched, bindings = [], [], Counter(), []

    def mismatch(condition, code):
        if not condition:
            issues.append(code)

    mismatch(review.get('html_url') == target + '#pullrequestreview-' + str(review_id),
             'REVIEW_TARGET_DIFFERS')
    if 'pull_request_url' in review:
        mismatch(review['pull_request_url'] == api_pull_request(target), 'REVIEW_API_TARGET_DIFFERS')
    mismatch(review.get('commit_id') == request['commit_id'], 'REVIEW_COMMIT_DIFFERS')
    mismatch(review.get('body') == request['body'], 'REVIEW_BODY_DIFFERS')
    mismatch(reviewer is None or author == reviewer, 'REVIEW_AUTHOR_DIFFERS')
    state = review.get('state')
    submitted = type(review.get('submitted_at')) is str and bool(review['submitted_at'])
    review_needed = state == 'PENDING' or not submitted
    if not review_needed:
        mismatch(state == STATES[request['event']], 'REVIEW_STATE_DIFFERS')
    mismatch(len(listed) == len(expected_rows), 'LISTED_COMMENT_COUNT_DIFFERS')
    mismatch(not set(details) - set(listed), 'DETAIL_NOT_IN_LIST')

    for identity, listed_row in listed.items():
        row = details.get(identity, listed_row)
        label = str(identity) + ':'
        for captured in (listed_row, row):
            mismatch(positive(captured.get('pull_request_review_id')) == review_id,
                     label + 'COMMENT_REVIEW_DIFFERS')
            mismatch(captured.get('html_url') == target + '#discussion_r' + str(identity),
                     label + 'COMMENT_TARGET_DIFFERS')
            if 'pull_request_url' in captured:
                mismatch(captured['pull_request_url'] == api_pull_request(target),
                         label + 'COMMENT_API_TARGET_DIFFERS')
            mismatch(login(captured) == author, label + 'COMMENT_AUTHOR_DIFFERS')
            mismatch(captured.get('in_reply_to_id') is None, label + 'COMMENT_IS_REPLY')
        for field in ('body', 'path', 'original_commit_id', 'original_line',
                      'original_start_line', 'side', 'start_side'):
            if field in listed_row and field in row:
                mismatch(listed_row[field] == row[field], label + 'LIST_DETAIL_' + field.upper())
        # Diff position is an offset, not a source line. Never use it as one.
        original = row.get('original_commit_id')
        mismatch(original is None or original == request['commit_id'],
                 label + 'ORIGINAL_COMMIT_DIFFERS')
        for field in ('line', 'original_line', 'start_line', 'original_start_line'):
            if field in row and row[field] is not None:
                positive(row[field])
        if (original == request['commit_id'] and type(row.get('original_line')) is int
                and 'original_start_line' in row):
            line, start, mode = row['original_line'], row.get('original_start_line'), 'original'
            if row.get('commit_id') == request['commit_id'] and row.get('line') is not None:
                mismatch(row['line'] == line, label + 'ANCHOR_DISAGREEMENT')
        elif (row.get('commit_id') == request['commit_id'] and type(row.get('line')) is int
              and 'start_line' in row):
            line, start, mode = row['line'], row.get('start_line'), 'current_exact_commit'
        else:
            missing.append(identity)
            continue
        if row.get('side') not in ('LEFT', 'RIGHT') or 'start_side' not in row:
            missing.append(identity)
            continue
        if start is not None and row.get('start_side') not in ('LEFT', 'RIGHT'):
            missing.append(identity)
            continue
        normalized = {'path': row.get('path'), 'body': row.get('body'), 'line': line,
                      'side': row['side'], 'start_line': start,
                      'start_side': row.get('start_side') if start is not None else None}
        require(type(normalized['path']) is str and type(normalized['body']) is str,
                'missing captured comment path/body')
        positive(line)
        if start is not None:
            positive(start)
        key = fingerprint(normalized)
        matched[key] += 1
        mismatch(matched[key] <= expected[key], label + 'COMMENT_NOT_REQUESTED')
        bindings.append({'id': identity, 'anchor': mode, 'path': normalized['path'],
                         'line': line, 'side': normalized['side'], 'start_line': start,
                         'start_side': normalized['start_side'],
                         'body_sha256': hashlib.sha256(normalized['body'].encode()).hexdigest()})
    if not missing:
        mismatch(matched == expected, 'COMMENT_MULTISET_DIFFERS')
    if issues:
        decision, action = 'CAPTURE_MISMATCH', 'INSPECT_CAPTURE'
    elif review_needed:
        decision, action = 'REVIEW_DETAILS_NEEDED', 'READ_REVIEW'
    elif missing:
        decision, action = 'COMMENT_DETAILS_NEEDED', 'READ_COMMENT_DETAILS'
    else:
        decision, action = 'CAPTURED_REVIEW_MATCHES_REQUEST', 'RETAIN_CAPTURE'
    return {'schema': 'gooo/review-readback/v1', 'decision': decision,
            'next_action': action, 'pull_request': target, 'review_id': review_id,
            'reviewer': author, 'requested_commit': request['commit_id'],
            'requested_comments': len(expected_rows), 'captured_comment_anchors': len(bindings),
            'missing_comment_ids': sorted(set(missing)), 'issues': sorted(set(issues)),
            'comment_bindings': sorted(bindings, key=lambda row: row['id']),
            'remote_freshness_established': False, 'source_authenticated': False,
            'patch_approval_verified': False, 'publication_effects': 0,
            'repost_recommended': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pull-request', 'request', 'review', 'comments', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--details')
    parser.add_argument('--reviewer')
    args = parser.parse_args(argv)
    out = Path(args.out)
    try:
        out.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 2
    report = {'schema': 'gooo/review-readback/v1', 'decision': 'INVALID_CAPTURE',
              'next_action': 'INSPECT_CAPTURE', 'source_authenticated': False,
              'remote_freshness_established': False, 'patch_approval_verified': False,
              'publication_effects': 0, 'repost_recommended': False}
    try:
        values = {}
        for name in ('request', 'review', 'comments', 'details'):
            path = getattr(args, name)
            if path is None:
                values[name] = []
                continue
            raw = capture(path)
            (out / (name + '.original')).write_bytes(raw)
            values[name] = decode(raw)
        report = check(**values, target=args.pull_request, reviewer=args.reviewer)
    except (OSError, ValueError, TypeError, RecursionError) as error:
        report['error'] = str(error)
    for name in ('check_review_readback.py', 'compare_go_tests.py', 'compare_js.py'):
        (out / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    report['sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(out.iterdir()) if p.is_file()}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=True))
    if report['decision'] == 'INVALID_CAPTURE':
        return 2
    return 0 if report['decision'] == 'CAPTURED_REVIEW_MATCHES_REQUEST' else 1


if __name__ == '__main__':
    raise SystemExit(main())
