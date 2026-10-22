"""Verify both engine adapters against source-pinned observed boundaries."""
from argparse import Namespace
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.compare_js import compare, sha, snapshots, typed

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/js-differential'
BASE = 'a6ef56644a78f34dfcd246aa8acf03ad659f1c4e'
HEAD = '64adc8bb4d51821549c138900ca6bc31194f403d'


def expected_rows(native):
    samples = [
        ('lone-high', [55296], [55296], [55296]),
        ('lone-low', [57343], [57343], [57343]),
        ('separated', [55296, 101, 769, 57343], [55296, 233, 57343], [55296, 101, 769, 57343]),
        ('valid-pair', [55357, 56898], [55357, 56898], [55357, 56898]),
        ('combining', [101, 769], [233], [101, 769]),
        ('replacement', [65533], [65533], [65533]),
    ]
    rows = []
    for name, value, composed, decomposed in samples:
        for form in ('NFC', 'NFD', 'NFKC', 'NFKD'):
            result = composed if form in ('NFC', 'NFKC') else decomposed
            if native and name in ('lone-high', 'lone-low', 'separated'):
                result = [65533 if 0xd800 <= n <= 0xdfff else n for n in result]
            rows.append(dict(id=name + '/' + form, input=value, result=result))
    return snapshots(json.dumps(rows).encode())


def verify_goja():
    report = compare(Namespace(script=ROOT / 'examples/js-differential/normalize.js',
                               base=BASE, head=HEAD, head_ref=None, node='node', seconds=30, out=OUT))
    summary = {'schema': 'gooo-language-bridge/js-driver-check/v1', 'decision': 'FAIL_CLOSED',
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
               'scope': 'Driver verification reproduces known differences; it does not approve Goja normalization.'}
    try:
        expected = {name + '/' + form for name in ('lone-high', 'lone-low', 'separated')
                    for form in ('NFC', 'NFD', 'NFKC', 'NFKD')}
        if (report['decision'] != 'DIFFERENCES' or report.get('cases') != 24
                or set(report['ids']['head_differences']) != expected
                or report['counts'] != dict(head_differences=12, corrected=0, introduced=0,
                                            unchanged_differences=12, changed_but_still_differs=0)):
            raise ValueError('known differential outcome differs')
        for name in ('node', 'head', 'base'):
            actual = snapshots((OUT / (name + '.stdout')).read_bytes())
            if typed(actual) != typed(expected_rows(name != 'node')):
                raise ValueError('original units or normalized outputs differ: ' + name)
        summary.update(decision='PASS', cases=24, expected_known_differences=12,
                       driver_decision=report['decision'], elapsed_seconds=report['elapsed_seconds'])
    except (OSError, ValueError, KeyError, TypeError) as error:
        summary['error'] = str(error)
    finally:
        summary['sha256'] = {p.name: sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != 'summary.json'}
        summary['sha256']['tools/verify_js_comparison.py'] = sha(Path(__file__))
        (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


def verify_sobek():
    out = ROOT / 'evidence/js-sobek'
    report = compare(Namespace(engine='sobek', script=ROOT / 'examples/js-differential/json-reviver.js',
                               base='87a47258b7dcb6579c5cdfebbe07a9a1203cb719',
                               head='6713561da465808c4f0bc73c7eb447a921a05092',
                               head_ref=None, node='node', seconds=30, out=out))
    summary = {'schema': 'gooo-language-bridge/js-sobek-check/v1', 'decision': 'FAIL_CLOSED',
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
               'scope': 'Finite snapshots of Sobek PR 165; no conformance or upstream approval verdict.'}
    try:
        corrected = {'scalar/null', 'array/null', 'object/null'}
        if (report['decision'] != 'MATCH' or report.get('cases') != 54
                or report.get('repository') != 'https://github.com/grafana/sobek.git'
                or report.get('module') != 'github.com/grafana/sobek'
                or set(report['ids']['corrected']) != corrected
                or report['counts'] != dict(head_differences=0, corrected=3, introduced=0,
                                            unchanged_differences=0, changed_but_still_differs=0)):
            raise ValueError('Sobek differential outcome differs')
        actual = {name: snapshots((out / (name + '.stdout')).read_bytes()) for name in ('node', 'head', 'base')}
        if typed(actual['node']) != typed(actual['head']):
            raise ValueError('head snapshots differ from reference')
        noncallable = ('undefined', 'null', 'boolean', 'number', 'nan', 'string',
                       'object', 'array', 'symbol', 'bigint', 'poison-object', 'revoked-object')
        for root, text in [('scalar', '42'), ('array', '[1,{"value":2}]'), ('object', '{"value":42}')]:
            for kind in noncallable:
                id = root + '/' + kind
                expected = snapshots(json.dumps([dict(id=id, input=dict(json=text, reviver=kind),
                                                      result=dict(value=json.loads(text), calls=[]))]).encode())[id]
                for name in ('node', 'head') if kind == 'null' else ('node', 'head', 'base'):
                    if typed(actual[name][id]) != typed(expected):
                        raise ValueError('non-callable reviver was not ignored: ' + name + '/' + id)
                if kind == 'null':
                    if typed(actual['base'][id]['result']) != typed(dict(error='TypeError', calls=[])):
                        raise ValueError('base null-reviver failure differs')
        for name in ('head', 'base'):
            if report['providers'][name].get('engine') != 'sobek':
                raise ValueError('provider engine identity differs')
        summary.update(decision='PASS', cases=54, corrected=3, introduced=0,
                       driver_decision=report['decision'], elapsed_seconds=report['elapsed_seconds'])
    except (OSError, ValueError, KeyError, TypeError) as error:
        summary['error'] = str(error)
    finally:
        summary['sha256'] = {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file() and p.name != 'summary.json'}
        summary['sha256']['tools/verify_js_comparison.py'] = sha(Path(__file__))
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


def main():
    goja = verify_goja()
    sobek = verify_sobek()
    return 0 if goja == sobek == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
