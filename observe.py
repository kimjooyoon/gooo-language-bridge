"""Run two existing, unmodified test groups on two pinned revisions."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parent
SDK = Path('/Users/alice/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.27.3.darwin-arm64')
REFS = json.loads((ROOT / 'preparation.json').read_text())['refs']
FILTER = '^(TestIssue1109_TextUnmarshalerNamedScalarKinds|TestUnmarshal_Floats)$'
ENV = {k: os.environ[k] for k in ('HOME', 'TMPDIR', 'LANG', 'LC_ALL') if k in os.environ}
ENV.update({'PATH': str(SDK / 'bin') + ':/usr/bin:/bin:/usr/sbin:/sbin', 'GOROOT': str(SDK),
            'GOTOOLCHAIN': 'local', 'GOENV': 'off', 'GOWORK': 'off', 'GOPROXY': 'off',
            'GOSUMDB': 'off', 'GOFLAGS': '-mod=readonly', 'GOMAXPROCS': '2', 'CGO_ENABLED': '0'})

def sha(data):
    return hashlib.sha256(data).hexdigest()

def snapshot(label):
    cwd = ROOT / label
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=cwd, text=True).strip() == REFS[label]
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=cwd)
    rows = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=cwd).split(b'\0')
    result = {}
    for row in rows:
        if not row:
            continue
        metadata, name = row.split(b'\t', 1)
        mode, expected, stage = metadata.split()
        assert stage == b'0' and mode != b'160000'
        path = cwd / os.fsdecode(name)
        data = os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes()
        assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == expected.decode()
        result[os.fsdecode(name)] = sha(data)
    return result

def run(label, argv, cwd, deadline):
    start = time.monotonic()
    expired = False
    with (ROOT / (label + '.stdout')).open('wb') as out, (ROOT / (label + '.stderr')).open('wb') as err:
        child = subprocess.Popen(argv, cwd=cwd, env=ENV, stdout=out, stderr=err, start_new_session=True)
        try:
            child.wait(timeout=deadline)
        except subprocess.TimeoutExpired:
            expired = True
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=3)
        finally:
            try:
                os.killpg(child.pid, 0)
            except ProcessLookupError:
                group_closed = True
            else:
                os.killpg(child.pid, signal.SIGKILL)
                group_closed = False
            if child.poll() is None:
                child.wait(timeout=3)
    return {'label': label, 'argv': argv, 'exit_code': child.returncode,
            'deadline_seconds': deadline, 'deadline_exceeded': expired,
            'seconds': round(time.monotonic() - start, 6), 'process_group_closed': group_closed,
            'stdout_sha256': sha((ROOT / (label + '.stdout')).read_bytes()),
            'stderr_sha256': sha((ROOT / (label + '.stderr')).read_bytes())}

def main():
    assert not (ROOT / 'observation.json').exists(), 'Preserve original observations; do not overwrite'
    before = {label: snapshot(label) for label in REFS}
    sections = []
    for label in REFS:
        source = (ROOT / label / 'unmarshaler_test.go').read_text()
        begin = source.index('// Issue #1109: encoding.TextUnmarshaler')
        end = source.index('// Issue #1109: same regression for date and time', begin)
        sections.append(source[begin:end])
    assert sections[0] == sections[1], 'Named-scalar regression group differs'
    (ROOT / 'existing-named-scalar-tests.txt').write_text(sections[0])
    report = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'revisions': REFS,
              'environment': ENV, 'test_filter': FILTER, 'source_before': before,
              'same_named_scalar_test_section_sha256': sha(sections[0].encode()),
              'supervisor_sha256': sha(Path(__file__).read_bytes()), 'runs': [],
              'scope': 'Two existing test groups only; no new test, production patch, race/coverage/benchmark/capability claim'}
    try:
        report['runs'].append(run('go-version', [str(SDK / 'bin/go'), 'version'], ROOT, 5))
        for label in REFS:
            observed = run(label, [str(SDK / 'bin/go'), 'test', '-count=1', '-timeout=15s', '-p=2', '-json', '-run', FILTER, '.'], ROOT / label, 45)
            report['runs'].append(observed)
            observed['results'] = [{'test': e.get('Test'), 'action': e['Action']} for line in (ROOT / (label + '.stdout')).read_text().splitlines()
                                   if (e := json.loads(line))['Action'] in ('pass', 'fail', 'skip')]
            observed['failures'] = [e for e in observed['results'] if e['action'] == 'fail']
            observed['skips'] = [e for e in observed['results'] if e['action'] == 'skip']
        report['source_after'] = {label: snapshot(label) for label in REFS}
        assert before == report['source_after']
        report['completed'] = True
    finally:
        (ROOT / 'observation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'completed': report['completed'], 'runs': [{k:v for k,v in r.items() if k != 'results'} for r in report['runs']]}, indent=2))

if __name__ == '__main__':
    main()
