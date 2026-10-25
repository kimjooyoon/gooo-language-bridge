"""Offline integrity audit of this workbench's complete CI evidence bundle."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SUMMARIES = {
    'summary.json': 'run',
    'candidate-policy/summary.json': 'candidate-review',
    'chroma-go-numbers/summary.json': 'chroma-go-numbers',
    'chroma-gooo/summary.json': 'upstream-checks',
    'completion-intent/summary.json': 'completion-intent',
    'division-comparison/summary.json': 'division-comparison',
    'forward-delete/summary.json': 'forward-delete',
    'highlighter-first-error/summary.json': 'highlighter-first-error',
    'js-differential/summary.json': 'js-driver-check',
    'js-sobek/summary.json': 'js-sobek-check',
    'read-reset/summary.json': 'read-reset',
    'text-length/summary.json': 'text-length',
    'yaegi-1736/summary.json': 'upstream-regression',
}
BASE_SUMMARIES = dict(SUMMARIES)
SUMMARIES['input-defaults/summary.json'] = 'input-defaults'
INPUT_DEFAULTS_SUMMARIES = dict(SUMMARIES)
SUMMARIES['hcl-null-defaults/summary.json'] = 'hcl-null-defaults'
HCL_DEFAULTS_SUMMARIES = dict(SUMMARIES)
SUMMARIES['response-planning/summary.json'] = 'response-planning'
RESPONSE_PLANNING_SUMMARIES = dict(SUMMARIES)
SUMMARIES['contribution-profiles/summary.json'] = 'contribution-profiles'
CONTRIBUTION_PROFILES_SUMMARIES = dict(SUMMARIES)
SUMMARIES['producer-response/summary.json'] = 'producer-response'
LEGACY = {'chroma-gooo/summary.json', 'yaegi-1736/summary.json'}
REPORTS = {'js-differential/report.json', 'js-sobek/report.json'}
SOURCE_ROOTS = {'bridges', 'tools', 'examples', 'tests', 'proposals'}
MAX_BYTES = 256 * 1024 * 1024
MAX_FILES = 2048


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_path(name):
    require(type(name) is str and name and '\\' not in name and ':' not in name and '\x00' not in name,
            'invalid evidence path')
    path = PurePosixPath(name)
    require(path.parts and not path.is_absolute() and str(path) == name
            and all(part not in ('.', '..') for part in path.parts), 'unsafe evidence path: ' + name)
    return path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError('nonfinite JSON constant: ' + value)


def read_json(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_object,
                      parse_constant=invalid_constant)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def audit(artifact, source_revision, execution_revision, run_id, repository=ROOT):
    require(all(type(s) is str and re.fullmatch(r'[0-9a-f]{40}', s)
                for s in (source_revision, execution_revision)), 'expected full lowercase Git SHAs')
    require(type(run_id) is str and re.fullmatch(r'[1-9][0-9]*', run_id), 'expected positive run ID')
    repository = Path(repository).resolve()
    git = ['git', '--no-replace-objects', '-C', str(repository)]
    git_env = dict(os.environ, GIT_NO_LAZY_FETCH='1')
    require(subprocess.check_output(git + ['cat-file', '-t', source_revision], timeout=10,
                                    stderr=subprocess.PIPE, env=git_env).strip() == b'commit',
            'source revision is not a local commit')
    markers = ['bridges/input-defaults/gooo.workspace.json', 'bridges/hcl-null-defaults/gooo.workspace.json',
               'bridges/contribution-response/gooo.workspace.json',
               'bridges/contribution-profiles/gooo.workspace.json',
               'bridges/producer-response/contract.json']
    present = subprocess.check_output(git + ['ls-tree', '--name-only', source_revision, '--'] + markers,
                                      timeout=10, stderr=subprocess.PIPE, env=git_env).decode().splitlines()
    require(set(present) <= set(markers), 'unexpected source inventory marker')
    require(markers[1] not in present or markers[0] in present, 'inconsistent source inventory markers')
    require(markers[2] not in present or markers[1] in present, 'inconsistent source inventory markers')
    require(markers[3] not in present or markers[2] in present, 'inconsistent source inventory markers')
    require(markers[4] not in present or markers[3] in present, 'inconsistent source inventory markers')
    if markers[4] in present:
        summaries, inventory = SUMMARIES, 'producer-response-18'
    elif markers[3] in present:
        summaries, inventory = CONTRIBUTION_PROFILES_SUMMARIES, 'contribution-profiles-17'
    elif markers[2] in present:
        summaries, inventory = RESPONSE_PLANNING_SUMMARIES, 'response-planning-16'
    elif markers[1] in present:
        summaries, inventory = HCL_DEFAULTS_SUMMARIES, 'hcl-null-defaults-15'
    elif markers[0] in present:
        summaries, inventory = INPUT_DEFAULTS_SUMMARIES, 'input-defaults-14'
    else:
        summaries, inventory = BASE_SUMMARIES, 'base-13'
    artifact = Path(artifact)
    require(not artifact.is_symlink() and artifact.is_dir(), 'expected an extracted artifact directory')
    artifact = artifact.resolve()
    files = {}
    total = 0
    for entry, path in enumerate(artifact.rglob('*')):
        require(entry < MAX_FILES * 2, 'too many evidence entries')
        require(not path.is_symlink(), 'symlink in evidence bundle')
        if not path.is_file():
            require(path.is_dir(), 'nonregular evidence entry')
            continue
        name = path.relative_to(artifact).as_posix()
        safe_path(name)
        total += path.stat().st_size
        require(total <= MAX_BYTES and len(files) < MAX_FILES, 'evidence bundle exceeds audit bounds')
        files[name] = path
    require({n for n in files if n.endswith('/summary.json') or n == 'summary.json'}
            == set(summaries), 'missing or unexpected summary inventory')
    require({n for n in files if n.endswith('/report.json') or n == 'report.json'}
            == REPORTS, 'missing or unexpected native report inventory')
    source_cache = {}
    artifact_cache = {}
    covered = set()
    checked = 0
    contexts = 0
    fingerprints = {}

    def artifact_bytes(name):
        require(name in files, 'missing captured file: ' + name)
        if name not in artifact_cache:
            artifact_cache[name] = files[name].read_bytes()
        covered.add(name)
        return artifact_cache[name]

    def source_bytes(name):
        if name not in source_cache:
            source_cache[name] = subprocess.check_output(
                git + ['cat-file', 'blob', source_revision + ':' + name], timeout=10, stderr=subprocess.PIPE, env=git_env)
        return source_cache[name]

    for name in sorted(set(summaries) | REPORTS):
        document = read_json(files[name])
        require(type(document) is dict, 'expected manifest object: ' + name)
        native = name in REPORTS
        schema = 'js-differential' if native else summaries[name]
        require(document.get('schema') == 'gooo-language-bridge/' + schema + '/v1',
                'unexpected schema: ' + name)
        require(document.get('decision') in ({'MATCH', 'DIFFERENCES'} if native else {'PASS'}),
                'unsuccessful or malformed manifest: ' + name)
        if name not in LEGACY or 'commit' in document or 'run_id' in document:
            require(document.get('commit') == execution_revision
                    and type(document.get('run_id')) is str and document['run_id'] == run_id,
                    'execution tuple mismatch: ' + name)
            contexts += 1
        hashes = document.get('sha256')
        require(type(hashes) is dict and hashes, 'missing file hashes: ' + name)
        fingerprints[name] = digest(files[name].read_bytes())
        for target, expected in hashes.items():
            path = safe_path(target)
            require(type(expected) is str and re.fullmatch(r'(sha256:)?[0-9a-f]{64}', expected),
                    'invalid digest: ' + name)
            if not native and path.parts[0] == 'evidence':
                captured = '/'.join(path.parts[1:])
                data = artifact_bytes(captured)
            elif not native and path.parts[0] in SOURCE_ROOTS:
                data = source_bytes(target)
            else:
                require(len(path.parts) == 1, 'unexpected retained-file path: ' + target)
                parent = PurePosixPath(name).parent
                captured = str(parent / path)
                data = artifact_bytes(captured)
            require(digest(data) == expected.removeprefix('sha256:'),
                    'digest mismatch: ' + name + ' -> ' + target)
            checked += 1
    # Manifests and this audit's output are intentionally not self-hashed.
    uncovered = set(files) - covered - set(summaries) - {'integrity-audit.json'}
    require(not uncovered, 'unhashed captured files: ' + ', '.join(sorted(uncovered)))
    return dict(schema='gooo-language-bridge/evidence-integrity/v1', decision='PASS_INTEGRITY',
                source_revision=source_revision, execution_revision=execution_revision, run_id=run_id,
                summaries=len(summaries), source_inventory=inventory, native_reports=len(REPORTS), bound_contexts=contexts,
                legacy_context_exceptions=sorted(LEGACY), hash_references=checked,
                captured_files=len(covered), source_files=len(source_cache), manifest_sha256=fingerprints,
                scope='Captured file integrity against local Git source and the supplied execution tuple; '
                      'does not authenticate GitHub metadata, re-execute runtimes or certify semantics.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--execution-revision', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--repository', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = audit(args.artifact, args.source_revision, args.execution_revision, args.run_id, args.repository)
    except (OSError, ValueError, RecursionError, subprocess.SubprocessError) as error:
        print(json.dumps(dict(decision='FAIL_CLOSED', error=str(error))), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
