"""Local public-source pilot; never claims a private holdout or maintainer review."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from skills.factory_assurance import evaluate_assurance
from importlib.metadata import distribution

installed = distribution('botte-secrete')
assert installed.version == '2.0.0rc1'
assert json.loads(installed.read_text('direct_url.json'))['vcs_info']['commit_id'] == 'd98505fd6586ff3d0d32a2cb4ebd5f0408d4142a'

ROOT = Path.cwd()
UPSTREAM = ROOT / 'upstream'
EXPECTED = 'fee5aa338d3bd7a9e36c269e33b496a7848edc44'
env = os.environ.copy()
env.pop('PYTHONPATH', None)
env.pop('PYTHONHOME', None)
home = ROOT / 'isolated-home'
home.mkdir(exist_ok=True)
env.update(HOME=str(home), USERPROFILE=str(home), PYTHONUTF8='1',
           PYTHONIOENCODING='utf-8', BOTTE_NN_AUTO_LABELS='0',
           GIT_AUTHOR_NAME='Local pilot', GIT_AUTHOR_EMAIL='pilot@example.invalid',
           GIT_COMMITTER_NAME='Local pilot', GIT_COMMITTER_EMAIL='pilot@example.invalid')

def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], env=env,
                                   text=True, encoding='utf-8').strip()

assert git(UPSTREAM, 'rev-parse', 'HEAD') == EXPECTED
assert not git(UPSTREAM, 'status', '--porcelain')
source = (UPSTREAM / 'slugify/slugify.py').read_text(encoding='utf-8')
mutations = {
    'baseline': None,
    'lowercase_removed': ('text = text.lower()', 'text = text'),
    'length_limit_removed': ('if max_length > 0:', 'if False:'),
    'stopwords_removed': ('if stopwords:', 'if False:'),
}
# Freeze the cases and expected external-test outcomes before execution.
protocol = {
    'upstream_commit': EXPECTED,
    'scope': 'slugify package and upstream test.py',
    'mutations': mutations,
    'expected_tests': {k: ('pass' if v is None else 'fail') for k,v in mutations.items()},
    'expected_assurance': 'hold for every case: no private/external holdout',
    'judge': 'upstream public unittest assertions executed in separate processes',
    'independent_human_judge': False,
    'private_external_holdout': False,
}
(ROOT / 'protocol.json').write_text(json.dumps(protocol, indent=2), encoding='utf-8')
results = []
for name, mutation in mutations.items():
    case = ROOT / 'cases' / name
    case.mkdir(parents=True, exist_ok=False)
    shutil.copytree(UPSTREAM / 'slugify', case / 'slugify')
    for file in ('test.py', 'LICENSE'):
        shutil.copy2(UPSTREAM / file, case / file)
    if mutation:
        old, new = mutation
        assert source.count(old) == 1, old
        (case / 'slugify/slugify.py').write_text(source.replace(old, new), encoding='utf-8')
    test_hash = hashlib.sha256((case / 'test.py').read_bytes()).hexdigest()
    assert test_hash == hashlib.sha256((UPSTREAM / 'test.py').read_bytes()).hexdigest()
    git(case, 'init', '-q')
    git(case, 'add', 'slugify', 'test.py', 'LICENSE')
    tree = git(case, 'write-tree')
    sha = git(case, 'commit-tree', tree, '-m', 'Frozen local pilot: ' + name)
    started = time.perf_counter()
    proc = subprocess.run([sys.executable, '-B', '-m', 'unittest', '-v', 'test'],
                          cwd=case, env=env, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=60)
    output = proc.stdout + proc.stderr
    (case / 'tests.log').write_text(output, encoding='utf-8')
    count = re.search(r'Ran (\d+) tests?', output)
    valid_run = bool(count) and not re.search(r'^ERROR:', output, re.MULTILINE)
    results.append({'name': name, 'exit': proc.returncode, 'valid_run': valid_run,
                    'tests': int(count.group(1)) if count else None,
                    'failures': re.findall(r'^FAIL: (.+)$', output, re.MULTILINE),
                    'elapsed_seconds': round(time.perf_counter()-started, 3),
                    'sha': sha, 'tree': tree, 'upstream_test_sha256': test_hash})

baseline_pass = results[0]['valid_run'] and results[0]['exit'] == 0
mutants_killed = all(x['valid_run'] and x['failures'] and x['exit'] != 0 for x in results[1:])
for result in results:
    run = {
        'schema_version': 1, 'action_id': 'public-slugify-' + result['name'],
        'stage': 'shadow', 'requested_autonomy': 'shadow',
        'mission': {'goals': ['Evaluate controlled slugify mutations'],
                    'invariants': ['Keep upstream public tests unchanged'],
                    'non_goals': ['Upstream changes', 'Production certification'],
                    'forbidden_transformations': ['Weaken tests', 'Publish findings automatically'],
                    'within_mission': True},
        'actors': {'builder': 'local-mutation-harness', 'judge': 'upstream-public-unittest'},
        'effects': {'declared': ['local-isolated-source'],
                    'observed': ['local-isolated-source'], 'unresolved': []},
        'evidence': [{'name': 'upstream-public-tests', 'required': True,
                      'status': 'pass' if result['exit'] == 0 else 'fail'},
                     {'name': 'independent-human-review', 'required': True, 'status': 'missing'}],
        'controls': {'positive_control': 'pass' if baseline_pass else 'fail',
                     'negative_control': 'fail' if mutants_killed else 'missing',
                     'holdout_scope': 'public_upstream',
                     'historical_regressions_checked': False,
                     'adversarial_cases_checked': True},
        'identity': {'source_sha': result['sha'], 'build_sha': result['sha'],
                     'tested_sha': result['sha'], 'source_tree': result['tree'],
                     'build_tree': result['tree'], 'tested_tree': result['tree']},
    }
    result['assurance'] = evaluate_assurance(run)
    (ROOT / 'cases' / result['name'] / 'assurance-input.json').write_text(json.dumps(run, indent=2), encoding='utf-8')

report = {'upstream': 'https://github.com/un33k/python-slugify',
          'upstream_commit': EXPECTED, 'botte_version': '2.0.0rc1',
          'baseline_pass': baseline_pass, 'mutants_killed': mutants_killed,
          'all_correctly_held': all(x['assurance']['status'] == 'hold' for x in results),
          'results': results,
          'limits': ['Public tests, not private holdout', 'No maintainer involvement',
                     'No new upstream defect claimed', 'Same operator prepared and ran the pilot',
                     'Botte consumes test evidence; it does not discover these defects itself']}
(ROOT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
raise SystemExit(0 if baseline_pass and mutants_killed and report['all_correctly_held'] else 1)
