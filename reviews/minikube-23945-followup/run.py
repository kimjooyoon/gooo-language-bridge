#!/usr/bin/env python3
"""Run the unchanged captured workflow harness against the bound minikube head."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
EXPECTED_HEAD = '4331e26157df2b298af011c1e922f2c04c80f512'
EXPECTED_HARNESS = '3d5a7e2d41a31f0c7e921b9ef227560de9d997de0cd8129fd448d90cce9680d6'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='minikube checkout at the exact tested head')
    parser.add_argument('--output', type=Path, required=True, help='new output directory; must not exist')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    binding = json.loads((HERE / 'tested-source.json').read_text())
    working = json.loads((HERE / 'working-source.json').read_text())
    if binding['head'] != EXPECTED_HEAD:
        raise SystemExit('unexpected package source binding')
    if hashlib.sha256((HERE / 'verify_workflow_pipelines.py').read_bytes()).hexdigest() != EXPECTED_HARNESS:
        raise SystemExit('captured harness has changed')

    # A missing object must fail locally rather than trigger a partial-clone fetch.
    blocked = {'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
               'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
               'GIT_CONFIG_PARAMETERS', 'GIT_CONFIG_COUNT', 'GIT_PREFIX'}
    for key in list(os.environ):
        if key in blocked or key.startswith(('GIT_CONFIG_KEY_', 'GIT_CONFIG_VALUE_')):
            os.environ.pop(key)
    os.environ['GIT_NO_LAZY_FETCH'] = '1'
    os.environ['GIT_TERMINAL_PROMPT'] = '0'

    def git(*command):
        return subprocess.check_output(['git', '-C', str(source), *command], timeout=10)

    if git('rev-parse', 'HEAD').decode().strip() != EXPECTED_HEAD:
        raise SystemExit('source HEAD differs from the tested revision')
    for path, expected in working['files'].items():
        raw = (source / path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected or raw != git('show', EXPECTED_HEAD + ':' + path):
            raise SystemExit('tested workflow differs: ' + path)
        git('cat-file', '-e', binding['base'] + ':' + path)
    output.mkdir(parents=True, exist_ok=False)
    checks = output / 'checks'
    checks.mkdir()
    (output / 'working-source.json').write_bytes((HERE / 'working-source.json').read_bytes())
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('captured_workflow_harness', HERE / 'verify_workflow_pipelines.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SOURCE, module.ROOT = source, checks
    module.main()


if __name__ == '__main__':
    main()
