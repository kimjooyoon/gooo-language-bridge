#!/usr/bin/env python3
"""Exercise captured minikube shell snippets against loopback HTTP only.

No Kubernetes, installer, sudo, cloud or credential operation is executed.
The curl adapter preserves source flags and redirects every URL to our server;
it also adds transport deadlines and disables user curl configuration.
"""
from pathlib import Path
import gzip
import hashlib
import http.server
import io
import json
import os
import re
import shutil
import signal
import subprocess
import tarfile
import threading
import time

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'source'
BASE = '34f70057d29a36eae8b8bec815b33ba1599ff80f'
FILES = ['Makefile', 'hack/prow/prow.mk',
         'hack/prow/installer/check_install_kubectl.sh',
         'hack/benchmark/time-to-k8s/time-to-k8s.sh',
         'hack/prow/integration_none_containerd_linux_x86.sh',
         'hack/jenkins/common.sh', 'hack/jenkins/minikube_set_pending.sh',
         '.github/workflows/smoke-test.yml', '.github/workflows/functional_test.yml']


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def function(text, name):
    match = re.search(r'^(?:function )?' + re.escape(name) + r'\(\) \{\n.*?^\}', text,
                      re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group()


def recipe(text, target):
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line == target + ':')
    body = []
    for line in lines[start + 1:]:
        if not line.startswith('\t'):
            break
        body.append(line)
    assert body
    return '\n'.join(body) + '\n'


def options(text):
    return '\n'.join(line for line in text.splitlines() if re.match(r'^set -[a-z]+', line))


def executable(path, text):
    path.write_text(text)
    path.chmod(0o755)


def archive_bytes():
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        content = b'#!/bin/sh\nexit 0\n'
        entry = tarfile.TarInfo('golangci-lint-9.9.9-linux-amd64/golangci-lint')
        entry.size, entry.mode = len(content), 0o755
        archive.addfile(entry, io.BytesIO(content))
    return output.getvalue()


ARCHIVE = archive_bytes()
CHECKSUMS = (digest(ARCHIVE) + '  golangci-lint-9.9.9-linux-amd64.tar.gz\n').encode()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', '0')))
        self.do_GET()

    def do_GET(self):
        state = self.server.case_state
        state['requests'].append({'method': self.command, 'path': self.path})
        mode, status = state['mode'], state['status']
        body = b'printf fixture-installed > "$INSTALL_MARKER"\n'
        code = 200
        if mode == 'single':
            code = status
        elif mode == 'lookup':
            if self.path.endswith('/stable.txt'):
                code, body = status, b'v1.99.0\n'
        elif mode == 'download':
            if self.path.endswith('/stable.txt'):
                body = b'v1.99.0\n'
            else:
                code = status
        elif mode == 'lint':
            if self.path.endswith('checksums.txt'):
                code, body = status, CHECKSUMS
            else:
                body = ARCHIVE
        elif mode == 'gh_lookup':
            code = status if self.path.endswith('/latest') else 200
        elif mode == 'gh_archive':
            code = status if self.path.endswith('.tar.gz') else 200
        elif mode == 'retry':
            code = status if len(state['requests']) == 1 else 201
            body = b'fixture status response\n'
        elif mode == 'retry_exhausted':
            code, body = status, b'fixture status response\n'
        self.send_response(code)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_case(case_dir, origin):
    case_dir.mkdir(parents=True)
    bins = case_dir / 'bin'
    bins.mkdir()
    (case_dir / 'tmp').mkdir()
    executable(bins / 'curl', '''#!/usr/bin/env python3
import json,os,pathlib,subprocess,sys,urllib.parse
args=sys.argv[1:]
with open(os.environ['CURL_LOG'],'a') as log: log.write(json.dumps(args)+'\\n')
mapped=[]
for a in args:
    if a.startswith(('http://','https://')):
        u=urllib.parse.urlsplit(a)
        a=os.environ['FIXTURE_ORIGIN']+u.path+('?' + u.query if u.query else '')
    elif a.startswith('/tmp/'):
        a=os.environ['FIXTURE_DIR']+'/tmp/'+a[5:]
    mapped.append(a)
raise SystemExit(subprocess.call(['/usr/bin/curl','--disable','--connect-timeout','2','--max-time','5',*mapped]))
''')
    executable(bins / 'sudo', '''#!/bin/sh
printf "%s\\n" "$*" >> "$STUB_LOG"
case "$1" in VMNET_INTERACTIVE=0) shift;; esac
case "$1" in bash|sh) exec /bin/bash;; esac
printf installed > "$INSTALL_MARKER"
''')
    executable(bins / 'go', '#!/bin/sh\ncase "$*" in "env GOOS") echo linux;; "env GOARCH") echo amd64;; *) exit 97;; esac\n')
    executable(bins / 'sleep', '#!/bin/sh\nprintf "%s\\n" "$*" >> "$SLEEP_LOG"\n')
    python = Path(shutil.which('python3')).resolve()
    (bins / 'python3').symlink_to(python)
    return {'PATH': str(bins) + ':/usr/bin:/bin:/usr/sbin:/sbin',
            'LC_ALL': 'C', 'TMPDIR': str(case_dir / 'tmp'),
            'FIXTURE_ORIGIN': origin, 'FIXTURE_DIR': str(case_dir),
            'INSTALL_MARKER': str(case_dir / 'installed'),
            'STUB_LOG': str(case_dir / 'stub.log'),
            'CURL_LOG': str(case_dir / 'curl.log'),
            'SLEEP_LOG': str(case_dir / 'sleep.log')}


def execute(command, cwd, env):
    with (cwd / 'stdout').open('wb') as out, (cwd / 'stderr').open('wb') as err:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=out, stderr=err,
                                start_new_session=True)
        try:
            return proc.wait(timeout=15)
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=5)


def case(snapshot, kind):
    if kind == 'single':
        path = 'hack/prow/integration_none_containerd_linux_x86.sh'
        line = next(l.strip() for l in snapshot[path].splitlines() if re.match(r'\s*curl ', l))
        return path, options(snapshot[path]) + '\nCRICTL_VERSION=v1.99.0\n' + line + '\nprintf continued > continued\n'
    if kind in ('lookup', 'download'):
        path = 'hack/prow/installer/check_install_kubectl.sh'
        return path, snapshot[path]
    if kind == 'pipeline':
        path = 'hack/benchmark/time-to-k8s/time-to-k8s.sh'
        return path, options(snapshot[path]) + '\n' + function(snapshot[path], 'install_k3d') + '\ninstall_k3d\nprintf continued > continued\n'
    if kind in ('smoke_pipeline', 'rootless_pipeline'):
        path = '.github/workflows/' + ('smoke-test.yml' if kind == 'smoke_pipeline' else 'functional_test.yml')
        name = 'Install vfkit and vmnet-helper (macos)' if kind == 'smoke_pipeline' else 'Set up Rootless Docker (rootless)'
        block = re.search(r'^      - name: ' + re.escape(name) + r'\n.*?(?=^      - name:|\Z)', snapshot[path], re.MULTILINE | re.DOTALL).group()
        # GitHub's explicit bash command adds pipefail; the unspecified bash fallback does not.
        shell_options = 'set -e -o pipefail' if re.search(r'^        shell: bash$', block, re.MULTILINE) else 'set -e'
        line = next(l.strip() for l in block.splitlines() if l.strip().startswith('curl '))
        return path, shell_options + '\n' + line + '\nprintf continued > continued\n'
    if kind == 'lint':
        path = 'Makefile'
        target = 'out/linters/golangci-lint-$(GOLINT_VERSION)'
        return path, 'GOLINT_VERSION=v9.9.9\nall: ' + target + '\n' + target + ':\n' + recipe(snapshot[path], target)
    if kind in ('gh_lookup', 'gh_archive'):
        path = 'hack/prow/prow.mk'
        return path, 'all:\n' + recipe(snapshot[path], 'install-gh-prow')
    if kind.startswith('retry'):
        path = 'hack/jenkins/minikube_set_pending.sh' if kind.endswith('_pending') else 'hack/jenkins/common.sh'
        return path, 'set -e\n' + function(snapshot[path], 'retry_github_status') + '\nretry_github_status deadbeef fixture pending fixture-token https://example.invalid fixture-description\nprintf continued > continued\n'
    raise AssertionError(kind)


def main():
    started = time.monotonic()
    run = HERE / ('http-validation-' + str(time.time_ns()))
    run.mkdir()
    snapshots = {
        'before': {p: subprocess.check_output(['git', 'show', BASE + ':' + p], cwd=SOURCE).decode() for p in FILES},
        'after': {p: (SOURCE / p).read_text() for p in FILES},
    }
    for version, files in snapshots.items():
        for p, content in files.items():
            path = run / 'sources' / version / p
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    scenarios = [(kind, mode, status) for kind, mode in [('single', 'single'), ('lookup', 'lookup'),
                  ('download', 'download'), ('pipeline', 'single'), ('smoke_pipeline', 'single'),
                  ('rootless_pipeline', 'single'), ('lint', 'lint'),
                  ('gh_lookup', 'gh_lookup'), ('gh_archive', 'gh_archive')]
                 for status in (200, 404, 500)]
    scenarios += [(kind, mode, status) for kind in ('retry_common', 'retry_pending')
                  for mode, status in [('retry', 500), ('retry_exhausted', 500)]]
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = []
    try:
        for version, snapshot in snapshots.items():
            for kind, mode, status in scenarios:
                label = f'{version}-{kind}-{mode}-{status}'
                folder = run / label
                env = make_case(folder, f'http://127.0.0.1:{server.server_port}')
                path, text = case(snapshot, kind)
                is_make = kind in ('lint', 'gh_lookup', 'gh_archive')
                source_file = folder / ('Makefile' if is_make else 'input.sh')
                source_file.write_text(text)
                if kind.startswith('gh_'):
                    for name in ('tar', 'mv', 'rm'):
                        executable(folder / 'bin' / name, '#!/bin/sh\nprintf "%s %s\\n" "' + name + '" "$*" >> "$STUB_LOG"\n')
                server.case_state = {'mode': mode, 'status': status, 'requests': []}
                cmd = ['/usr/bin/make', '--no-print-directory'] if is_make else ['/bin/bash', str(source_file), 'linux', 'amd64']
                code = execute(cmd, folder, env)
                requests = list(server.case_state['requests'])
                marker = (folder / 'installed').exists()
                continuation = (folder / 'continued').exists()
                installed_linter = (folder / 'out/linters/golangci-lint-v9.9.9').exists()
                stub = (folder / 'stub.log').read_text() if (folder / 'stub.log').exists() else ''
                extraction = any(line.startswith(('tar ', 'mv ')) for line in stub.splitlines())
                if kind.startswith('retry'):
                    count = 2 if mode == 'retry' else 8
                    passed = code == 0 and continuation and len(requests) == count
                elif status == 200:
                    passed = code == 0 and (installed_linter if kind == 'lint' else extraction if kind.startswith('gh_') else marker if kind in ('lookup', 'download', 'pipeline', 'smoke_pipeline', 'rootless_pipeline') else continuation)
                elif kind.startswith('gh_'):
                    passed = code != 0 and not extraction and len(requests) == (1 if kind == 'gh_lookup' else 2)
                else:
                    passed = code != 0 and not marker and not continuation and not installed_linter
                    if kind in ('lookup', 'lint'):
                        passed = passed and len(requests) == 1
                results.append({'label': label, 'version': version, 'source': path,
                                'source_sha256': digest(snapshot[path].encode()),
                                'fragment_sha256': digest(text.encode()), 'exit_code': code,
                                'http_status': status, 'requests': requests, 'installed': marker,
                                'continued': continuation, 'installed_linter': installed_linter,
                                'extraction_or_move_called': extraction, 'contract_pass': passed})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    report = {'base': BASE, 'run': str(run), 'elapsed_seconds': round(time.monotonic()-started,3),
              'source_files_unchanged_during_run': all((SOURCE/p).read_text() == s for p,s in snapshots['after'].items()),
              'limits': ['Loopback HTTP only; actual curl/bash/make, captured source fragments.',
                         'No installation, Kubernetes, full CI, real GitHub POST, authentication or real download claim.',
                         'curl URLs redirected to loopback; curl transport timeout/config isolation added by harness.',
                         'sudo and gh-recipe extraction/move commands are inert recorded stubs; go env is a fixed fixture.',
                         'Workflow checks use the source step shell selection and curl line, not an actual hosted Actions runner.',
                         'Existing status-post retry exhaustion remains successful by design.'],
              'results': results}
    report['counts'] = {v: {'pass': sum(x['contract_pass'] for x in results if x['version']==v),
                            'fail': sum(not x['contract_pass'] for x in results if x['version']==v)} for v in snapshots}
    report['decision'] = 'PASS' if report['counts']['after']['fail'] == 0 and report['source_files_unchanged_during_run'] else 'FAIL'
    (run / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
    (HERE / 'latest-http-validation.json').write_text(json.dumps({'report': str(run/'report.json'),'decision':report['decision']},indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('run','decision','counts','source_files_unchanged_during_run','elapsed_seconds')}))
    return 0 if report['decision']=='PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
