#!/usr/bin/env python3
"""Exercise complete saved Actions run blocks under the default bash -e.

Only curl talks to a loopback server. Every package manager, installer and Docker
operation is an inert, logged fixture. No hosted Actions job is started.
"""
from pathlib import Path
import hashlib
import http.server
import json
import os
import re
import signal
import subprocess
import threading
import time


ROOT = Path(__file__).resolve().parent
SOURCE = Path('/tmp/gooo-minikube-curl-20261027/source')
BASE = '34f70057d29a36eae8b8bec815b33ba1599ff80f'
FILES = {
    'rootless': ('.github/workflows/functional_test.yml', 'Set up Rootless Docker (rootless)'),
    'smoke': ('.github/workflows/smoke-test.yml', 'Install vfkit and vmnet-helper (macos)'),
}
LIMIT = 8 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def extract(text, name):
    lines = text.splitlines(keepends=True)
    first = next(i for i, line in enumerate(lines) if line.rstrip() == '      - name: ' + name)
    end = next((i for i in range(first + 1, len(lines)) if lines[i].startswith('      - name: ')), len(lines))
    block = ''.join(lines[first:end])
    assert not re.search(r'^        shell:', block, re.MULTILINE), 'default shell must be retained'
    start = next(i for i in range(first, end) if lines[i].rstrip() == '        run: |') + 1
    body = []
    for line in lines[start:end]:
        if line.strip():
            assert line.startswith('          '), repr(line)
            body.append(line[10:])
        else:
            body.append(line)
    return block, ''.join(body)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        state = self.server.state
        state['requests'].append({'method': 'GET', 'path': self.path, 'status': state['status']})
        body = b'printf installed > "$INSTALL_MARKER"\n'
        self.send_response(state['status'])
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def executable(path, text):
    path.write_text(text)
    path.chmod(0o755)


def prepare(folder, origin, prelude_failure, receiver_failure):
    folder.mkdir()
    bins = folder / 'bin'
    bins.mkdir()
    executable(bins / 'curl', '''#!/usr/bin/python3
import json, os, subprocess, sys, urllib.parse
args=sys.argv[1:]
with open(os.environ['CURL_LOG'], 'a') as out: out.write(json.dumps(args)+'\\n')
mapped=[]
for arg in args:
    if arg.startswith(('https://', 'http://')):
        parsed=urllib.parse.urlsplit(arg)
        arg=os.environ['LOOPBACK_ORIGIN']+parsed.path
    mapped.append(arg)
raise SystemExit(subprocess.call(['/usr/bin/curl', '--disable', '--connect-timeout', '2', '--max-time', '3', *mapped]))
''')
    executable(bins / 'sudo', '''#!/bin/sh
printf '%s\\n' "sudo $*" >> "$OPERATIONS_LOG"
case "$1" in
    apt-get) exit "$PRELUDE_FAILURE";;
    VMNET_INTERACTIVE=0) shift;;
esac
case "$1" in
    sh|bash)
        if [ "$RECEIVER_FAILURE" != 0 ]; then cat >/dev/null; exit "$RECEIVER_FAILURE"; fi
        exec /bin/bash;;
esac
exit 97
''')
    executable(bins / 'brew', '''#!/bin/sh
printf '%s\\n' "brew $*" >> "$OPERATIONS_LOG"
exit "$PRELUDE_FAILURE"
''')
    for command in ('dockerd-rootless-setuptool.sh', 'docker'):
        executable(bins / command, '''#!/bin/sh
printf '%s\\n' "${0##*/} $*" >> "$OPERATIONS_LOG"
exit 0
''')
    return {
        'PATH': str(bins) + ':/usr/bin:/bin',
        'LC_ALL': 'C',
        'CURL_LOG': str(folder / 'curl.jsonl'),
        'OPERATIONS_LOG': str(folder / 'operations.log'),
        'INSTALL_MARKER': str(folder / 'installed'),
        'LOOPBACK_ORIGIN': origin,
        'PRELUDE_FAILURE': str(prelude_failure),
        'RECEIVER_FAILURE': str(receiver_failure),
    }


def execute(folder, env):
    started = time.monotonic()
    with (folder / 'stdout').open('wb') as out, (folder / 'stderr').open('wb') as err:
        process = subprocess.Popen(['/bin/bash', '-e', str(folder / 'run.sh')], cwd=folder,
                                   env=env, stdout=out, stderr=err, start_new_session=True)
        error = None
        try:
            while process.poll() is None:
                if time.monotonic() - started > 8:
                    error = 'timeout'
                    break
                if os.fstat(out.fileno()).st_size > LIMIT or os.fstat(err.fileno()).st_size > LIMIT:
                    error = 'output limit'
                    break
                try:
                    process.wait(timeout=0.02)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    assert error is None, error
    return process.returncode, round(time.monotonic() - started, 6)


def main():
    started = time.monotonic()
    run = ROOT / ('workflow-pipelines-' + str(time.time_ns()))
    run.mkdir()
    before_hashes = {path: digest((SOURCE / path).read_bytes()) for path, _ in FILES.values()}
    frozen = json.loads((ROOT.parent / 'working-source.json').read_text())
    assert before_hashes == frozen['files']
    snapshots = {
        'before': {path: subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=SOURCE).decode() for path, _ in FILES.values()},
        'after': {path: (SOURCE / path).read_text() for path, _ in FILES.values()},
    }
    steps = {}
    for version, files in snapshots.items():
        steps[version] = {}
        for label, (path, name) in FILES.items():
            block, body = extract(files[path], name)
            captured = run / 'sources' / version / path
            captured.parent.mkdir(parents=True, exist_ok=True)
            captured.write_text(files[path])
            (run / f'{version}-{label}-step.txt').write_text(block)
            steps[version][label] = {'path': path, 'body': body, 'step_sha256': digest(block.encode()),
                                     'run_block_sha256': digest(body.encode()), 'file_sha256': digest(files[path].encode())}

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cases = []
    try:
        scenarios = [('http-200', 200, 0, 0), ('http-404', 404, 0, 0), ('http-500', 500, 0, 0),
                     ('prelude-failure', 200, 31, 0), ('receiver-failure', 200, 0, 37)]
        for version in ('before', 'after'):
            for label in FILES:
                for name, status, prelude_failure, receiver_failure in scenarios:
                    folder = run / f'{version}-{label}-{name}'
                    env = prepare(folder, f'http://127.0.0.1:{server.server_port}', prelude_failure, receiver_failure)
                    script = steps[version][label]['body'] + '\nprintf continued > continued\n'
                    (folder / 'run.sh').write_text(script)
                    server.state = {'status': status, 'requests': []}
                    code, elapsed = execute(folder, env)
                    continued, installed = (folder / 'continued').exists(), (folder / 'installed').exists()
                    request_count = len(server.state['requests'])
                    if name == 'http-200':
                        valid = code == 0 and continued and installed and request_count == 1
                    elif name == 'prelude-failure':
                        valid = code == 31 and not continued and not installed and request_count == 0
                    elif name == 'receiver-failure':
                        valid = code == 37 and not continued and not installed and request_count == 1
                    else:
                        valid = code != 0 and not continued and not installed and request_count == 1
                    captures = {p.name: {'sha256': digest(p.read_bytes()), 'bytes': p.stat().st_size}
                                for p in folder.iterdir() if p.is_file()}
                    cases.append({'version': version, 'step': label, 'scenario': name, 'exit_code': code,
                                  'continued': continued, 'installed': installed, 'request_count': request_count,
                                  'requests': list(server.state['requests']), 'pass': valid,
                                  'elapsed_seconds': elapsed, 'captures': captures})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    after_hashes = {path: digest((SOURCE / path).read_bytes()) for path, _ in FILES.values()}
    counts = {v: {'pass': sum(c['pass'] for c in cases if c['version'] == v),
                  'fail': sum(not c['pass'] for c in cases if c['version'] == v)} for v in snapshots}
    report = {
        'schema': 'gooo/minikube23945-default-shell-regression/v1',
        'base': BASE, 'prior_pr_head': frozen['parent'],
        'source_files': before_hashes, 'source_files_unchanged': before_hashes == after_hashes,
        'invocation': ['/bin/bash', '-e', 'run.sh'], 'steps': steps, 'cases': cases, 'counts': counts,
        'elapsed_seconds': round(time.monotonic() - started, 6),
        'harness_sha256': digest(Path(__file__).read_bytes()),
        'runtime': {'bash': subprocess.check_output(['/bin/bash', '--version']).decode().splitlines()[0],
                    'curl': subprocess.check_output(['/usr/bin/curl', '--version']).decode().splitlines()[0]},
        'limits': ['Complete captured run blocks, default Actions bash -e command emulated locally.',
                   'Real curl loopback HTTP; sudo/package-manager/installer/Docker commands are inert fixtures.',
                   'No hosted Actions run, installation, Kubernetes cluster or external download.'],
    }
    report_path = run / 'report.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    assert before_hashes == after_hashes
    assert counts == {'before': {'pass': 6, 'fail': 4}, 'after': {'pass': 10, 'fail': 0}}, counts
    pointer = {'report': str(report_path), 'report_sha256': digest(report_path.read_bytes()),
               'counts': counts, 'elapsed_seconds': report['elapsed_seconds'],
               'source_files': before_hashes, 'source_files_unchanged': True,
               'harness_sha256': report['harness_sha256']}
    (ROOT / 'latest-workflow-validation.json').write_text(json.dumps(pointer, indent=2) + '\n')
    print(json.dumps(pointer))


if __name__ == '__main__':
    main()
