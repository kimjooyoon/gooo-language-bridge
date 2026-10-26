"""One bounded, exact-source Caddy review experiment; emit receipts to job logs."""

import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time


REVISION = 'ab11ecd6aba5508fa82ac6fff5789d938cffa02c'
ORIGINAL_BLOB = '25a4af1e4c543280ff933baaca4d741ef3497e85'
REPOSITORY = 'https://github.com/caddyserver/caddy.git'
TARGET = 'modules/caddyhttp/fileserver/staticfiles.go'
PACKAGE = 'github.com/caddyserver/caddy/v2/modules/caddyhttp/fileserver'
TEST_FILE = 'precompressed_review_test.go'
MATRIX = 'TestPrecompressedServeContentResponseHeaders'
RANGE = 'TestPrecompressedRangeResponse'
ERRORS = 'TestPrecompressedErrorResponseHeaders'
LEAVES = {
    MATRIX + '/' + name for name in (
        'mismatched_If-Match', 'mismatched_If-Match_overridden_to_200',
        'matching_If-None-Match', 'matching_If-None-Match_overridden_to_200',
        'HEAD', 'mismatched_If-Range', 'unsatisfiable_range', 'multipart_range',
    )
} | {RANGE + '/' + name for name in ('full_response', 'range_response')} | {
    ERRORS + '/' + name for name in (
        'method_not_allowed', 'unreadable_etag_file_for_sidecar', 'invalid_status_code',
    )
}
BASELINE_FAILURES = {MATRIX + '/' + name for name in (
    'mismatched_If-Match', 'mismatched_If-Match_overridden_to_200', 'mismatched_If-Range',
)}
PARENTS = {MATRIX, RANGE, ERRORS}
ROOT = Path(__file__).resolve().parents[2]
PACKET = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_events(raw, before):
    runs, terminals = Counter(), defaultdict(list)
    output = defaultdict(str)
    package_terminal = []
    failed = set()
    event_count = 0
    for line in raw.decode('utf-8', errors='strict').splitlines():
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get('Action'), str):
            raise ValueError('invalid go test JSON event')
        event_count += 1
        action, name = row['Action'], row.get('Test')
        if row.get('FailedBuild') or action == 'build-fail':
            raise ValueError('go test reported a build failure')
        if action == 'build-output':
            continue
        if row.get('Package') != PACKAGE:
            raise ValueError('unexpected test package: ' + str(row.get('Package')))
        if name:
            if action == 'run':
                runs[name] += 1
            if action in ('pass', 'fail', 'skip'):
                terminals[name].append(action)
            if action == 'output':
                output[name] += row.get('Output', '')
            if action == 'fail':
                failed.add(name)
        elif action in ('pass', 'fail', 'skip'):
            package_terminal.append(action)
    expected_failures = BASELINE_FAILURES | {MATRIX} if before else set()
    if failed != expected_failures:
        raise ValueError('unexpected FAIL set: ' + repr(sorted(failed)))
    if package_terminal != ['fail' if before else 'pass']:
        raise ValueError('missing or incorrect package terminal event')
    for name in LEAVES | PARENTS:
        expected = 'fail' if name in expected_failures else 'pass'
        if runs[name] != 1 or terminals[name] != [expected]:
            raise ValueError('missing, repeated, skipped, or incorrect case: ' + name)
    if before:
        for name in BASELINE_FAILURES:
            text = output[name]
            if name.endswith('/mismatched_If-Range'):
                required = ['Content-Length = "", want sidecar length ']
            else:
                required = ['Content-Encoding = "gzip" on a non-content response, want unset',
                            'Content-Length = "', 'body length = 0, sidecar length = ']
            if not all(part in text for part in required):
                raise ValueError('expected header assertion evidence missing: ' + name)
    return {
        'event_count': event_count, 'package_terminal': package_terminal[0],
        'required_leaf_count': len(LEAVES),
        'required_leaves': {name: terminals[name][0] for name in sorted(LEAVES)},
        'all_terminal_counts': dict(Counter(a for states in terminals.values() for a in states)),
        'failed_tests': sorted(failed),
    }


def emit_files(out):
    # Base64 payloads are at most 16 KiB; the original bytes remain reconstructible.
    for path in sorted(out.iterdir()):
        if not path.is_file():
            continue
        print('EVIDENCE_FILE', path.name, path.stat().st_size, digest(path), flush=True)
        with path.open('rb') as stream:
            index = 0
            while chunk := stream.read(12 * 1024):
                print('EVIDENCE_CHUNK', path.name, index,
                      base64.b64encode(chunk).decode('ascii'), flush=True)
                index += 1
        print('EVIDENCE_END', path.name, flush=True)


def main():
    started = time.monotonic()
    deadline = started + 630
    report = {
        'schema': 'gooo-language-bridge/caddy-8205-review/v1', 'decision': 'FAIL_CLOSED',
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'source': {'repository': REPOSITORY, 'revision': REVISION,
                   'path': TARGET, 'original_git_blob': ORIGINAL_BLOB},
        'scope': 'native fileserver package review support; no upstream acceptance claim',
        'limits': {'total_seconds': 630, 'before_seconds': 480,
                   'per_test_binary_seconds': 60, 'per_stream_bytes': 8 * 1024 * 1024},
        'runtime': {'python': sys.version, 'system': platform.system(),
                    'release': platform.release(), 'machine': platform.machine()},
        'github': {key: os.environ.get(key) for key in (
            'GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT',
            'GITHUB_WORKFLOW', 'GITHUB_REF', 'GITHUB_JOB', 'RUNNER_OS', 'RUNNER_ARCH',
        )},
        'steps': [],
    }
    with tempfile.TemporaryDirectory(prefix='gooo-caddy8205-') as temporary:
        work = Path(temporary)
        out = work / 'evidence'
        out.mkdir()
        try:
            sys.path.insert(0, str(ROOT))
            from tools.compare_js import run_step

            helper = ROOT / 'tools/compare_js.py'
            for source, name in ((Path(__file__), 'runner.py'), (helper, 'run-step-helper.py'),
                                 (PACKET / 'production.patch', 'production.patch'),
                                 (PACKET / TEST_FILE, TEST_FILE)):
                if not source.is_file() or source.stat().st_size > 1024 * 1024:
                    raise ValueError('missing or oversized packet file: ' + source.name)
                shutil.copyfile(source, out / name)
            report['packet_sha256'] = {name: digest(out / name) for name in (
                'runner.py', 'run-step-helper.py', 'production.patch', TEST_FILE,
            )}
            env = dict(os.environ, GOTOOLCHAIN='local', GOMAXPROCS='2',
                       GOMEMLIMIT='512MiB', GOFLAGS='-mod=readonly', GOWORK='off',
                       GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1')
            report['environment'] = {key: env[key] for key in (
                'GOTOOLCHAIN', 'GOMAXPROCS', 'GOMEMLIMIT', 'GOFLAGS', 'GOWORK',
            )}

            def run(label, command, cwd=work, maximum=60, expected_exit=0):
                # Keep time for process-group cleanup and emitting the receipts.
                remaining = deadline - time.monotonic() - 10
                if remaining <= 0:
                    raise ValueError('total execution deadline exhausted')
                timeout = min(maximum, remaining)
                previous = len(report['steps'])
                try:
                    run_step(label, command, cwd, env, out, report['steps'], timeout=timeout)
                except ValueError:
                    record = report['steps'][-1]
                    if record.get('error') or record.get('exit_code') != expected_exit:
                        raise
                finally:
                    if len(report['steps']) > previous:
                        report['steps'][-1].update(command=command, cwd=str(cwd),
                                                  timeout_seconds=round(timeout, 3))
                if report['steps'][-1]['exit_code'] != expected_exit:
                    raise ValueError(label + ' returned an unexpected exit code')
                return (out / (label + '.stdout')).read_bytes()

            version = run('go-version', ['go', 'version']).decode().strip()
            if version.split()[2:3] != ['go1.27.3']:
                raise ValueError('expected pinned Go 1.27.3, got ' + version)
            report['go_version'] = version
            identity = json.loads(run('go-identity', ['go', 'env', '-json', 'GOVERSION',
                'GOOS', 'GOARCH', 'GOROOT', 'GOTOOLCHAIN', 'GOMODCACHE', 'GOCACHE',
                'GOPROXY', 'GOSUMDB', 'GOFLAGS', 'GOWORK']))
            if identity.get('GOOS') != 'linux':
                raise ValueError('expected the standard Linux runner')
            report['go_identity'] = identity
            run('git-init', ['git', 'init', '--object-format=sha1', '-q', 'source'])
            source = work / 'source'
            run('git-fetch', ['git', 'fetch', '--depth=1', REPOSITORY, REVISION], source, maximum=120)
            fetched = run('git-fetched', ['git', 'rev-parse', 'FETCH_HEAD'], source).decode().strip()
            if fetched != REVISION:
                raise ValueError('fetched revision differs from the pinned SHA')
            run('git-checkout', ['git', 'checkout', '--detach', REVISION], source)
            checked = run('git-head', ['git', 'rev-parse', 'HEAD'], source).decode().strip()
            blob = run('git-source-blob', ['git', 'rev-parse', 'HEAD:' + TARGET], source).decode().strip()
            work_blob = run('git-worktree-blob', ['git', 'hash-object', TARGET], source).decode().strip()
            if checked != REVISION or blob != ORIGINAL_BLOB or work_blob != ORIGINAL_BLOB:
                raise ValueError('source revision or immutable production blob differs')
            report['source'].update(fetched_revision=fetched, checked_revision=checked,
                                    observed_git_blob=blob, sha256=digest(source / TARGET))
            module_hashes = {name: digest(source / name) for name in ('go.mod', 'go.sum')}
            report['source']['module_sha256'] = module_hashes
            shutil.copyfile(source / TARGET, out / 'before-staticfiles.go')
            test = source / Path(TARGET).parent / TEST_FILE
            if test.exists():
                raise ValueError('review test already exists in the pinned source')
            shutil.copyfile(out / TEST_FILE, test)
            patch = out / 'production.patch'
            numstat = run('patch-scope', ['git', 'apply', '--numstat', str(patch)], source).decode()
            if len(numstat.splitlines()) != 1 or numstat.splitlines()[0].split('\t')[2:] != [TARGET]:
                raise ValueError('production patch must change exactly the pinned file')
            command = ['go', 'test', '-p=2', '-json', '-count=1', '-timeout=60s', '-short']
            focused = '^(' + '|'.join(sorted(PARENTS)) + ')$'
            before = run('before', command + ['-run', focused, './modules/caddyhttp/fileserver'],
                         source, maximum=480, expected_exit=1)
            report['before'] = inspect_events(before, before=True)
            if digest(source / TARGET) != report['source']['sha256']:
                raise ValueError('baseline test mutated the production source')
            run('patch-check', ['git', 'apply', '--check', str(patch)], source)
            run('patch-apply', ['git', 'apply', str(patch)], source)
            report['patched_source_sha256'] = digest(source / TARGET)
            shutil.copyfile(source / TARGET, out / 'after-staticfiles.go')
            after = run('after', command + ['./modules/caddyhttp/fileserver'], source, maximum=630)
            report['after'] = inspect_events(after, before=False)
            if digest(source / TARGET) != report['patched_source_sha256']:
                raise ValueError('after test mutated the production source')
            if digest(test) != report['packet_sha256'][TEST_FILE]:
                raise ValueError('review test changed during execution')
            if {name: digest(source / name) for name in module_hashes} != module_hashes:
                raise ValueError('module source files changed during validation')
            if time.monotonic() >= deadline:
                raise ValueError('total execution deadline exceeded')
            report['decision'] = 'PASS'
        except Exception as exc:
            report['error'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            report['elapsed_seconds'] = round(time.monotonic() - started, 3)
            report['files_sha256'] = {p.name: digest(p) for p in sorted(out.iterdir()) if p.is_file()}
            (out / 'summary.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
            emit_files(out)
    return 0 if report['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
