#!/usr/bin/env python3
"""Run the unchanged captured harness with an explicit checkout and output path."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='clean minikube checkout at the recorded candidate')
    parser.add_argument('--output', required=True, type=Path, help='new or empty directory for this run')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    source, output = args.source.resolve(), args.output.resolve()
    binding = json.loads((package / 'source-binding.json').read_text())
    harness = package / 'verify_http_failures.py'
    if hashlib.sha256(harness.read_bytes()).hexdigest() != binding['executed_harness_sha256']:
        parser.error('captured harness hash differs')
    # A partial clone must already have the required objects: never fetch them here.
    os.environ['GIT_NO_LAZY_FETCH'] = '1'
    git = ['git', '-C', str(source)]
    head = subprocess.check_output([*git, 'rev-parse', 'HEAD'], text=True).strip()
    if head != binding['candidate']:
        parser.error('checkout HEAD differs from the recorded candidate')
    subprocess.run([*git, 'diff', '--exit-code', '--quiet', 'HEAD'], check=True)
    for revision in (binding['base'], binding['candidate']):
        for row in binding['captured_http_sources']:
            subprocess.run([*git, 'cat-file', '-e', revision + ':' + row['path']], check=True)
    for row in binding['modified_files']:
        if hashlib.sha256((source / row['path']).read_bytes()).hexdigest() != row['sha256']:
            parser.error('checkout bytes differ: ' + row['path'])
    for command in ('/usr/bin/curl', '/bin/bash', '/usr/bin/make'):
        if not os.access(command, os.X_OK):
            parser.error('required command is unavailable: ' + command)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error('output must be new or empty; captured evidence is never overwritten')
    output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('captured_http_harness', harness)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    module.SOURCE = source
    module.HERE = output
    return module.main()


if __name__ == '__main__':
    raise SystemExit(main())
