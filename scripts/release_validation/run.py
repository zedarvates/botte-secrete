"""Reproduce RC1 installation and public-source pilot in a fresh environment."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv

HERE = Path(__file__).resolve().parent
UPSTREAM = 'fee5aa338d3bd7a9e36c269e33b496a7848edc44'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='New directory for public-safe JSON reports (must not exist).')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    root = Path(tempfile.mkdtemp(prefix='botte-rc1-reproduction-'))
    env = os.environ.copy()
    for key in ('PYTHONPATH', 'PYTHONHOME'):
        env.pop(key, None)
    home = root / 'home'
    home.mkdir()
    env.update(HOME=str(home), USERPROFILE=str(home), PYTHONUTF8='1',
               PYTHONIOENCODING='utf-8', BOTTE_NN_AUTO_LABELS='0',
               GIT_TERMINAL_PROMPT='0')
    results = []

    def execute(name: str, argv: list[str], cwd: Path = root, timeout: int = 300) -> None:
        with (root / (name + '.log')).open('w', encoding='utf-8') as log:
            try:
                proc = subprocess.run(argv, cwd=cwd, env=env, stdout=log,
                                      stderr=subprocess.STDOUT, timeout=timeout)
            except subprocess.TimeoutExpired:
                results.append({'step': name, 'passed': False, 'reason': 'timeout'})
                raise RuntimeError(name) from None
        results.append({'step': name, 'passed': proc.returncode == 0,
                        'exit': proc.returncode})
        if proc.returncode:
            raise RuntimeError(name)

    try:
        venv.EnvBuilder(with_pip=True).create(root / 'venv')
        python = root / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        execute('install', [str(python), '-m', 'pip', '--isolated', 'install',
                            '--no-cache-dir', '-r', str(HERE / 'requirements.txt')], timeout=600)
        smoke = root / 'smoke'
        smoke.mkdir()
        execute('smoke', [str(python), '-I', str(HERE / 'smoke.py')], smoke)
        shutil.copy2(smoke / 'smoke-report.json', output / 'installation.json')
        pilot = root / 'pilot'
        pilot.mkdir()
        upstream = pilot / 'upstream'
        execute('git-init', ['git', 'init', '-q', str(upstream)])
        execute('git-remote', ['git', '-C', str(upstream), 'remote', 'add', 'origin',
                               'https://github.com/un33k/python-slugify.git'])
        execute('git-fetch', ['git', '-C', str(upstream), 'fetch', '--depth=1', 'origin', UPSTREAM])
        execute('git-checkout', ['git', '-C', str(upstream), 'checkout', '--detach', UPSTREAM])
        execute('pilot', [str(python), '-I', str(HERE / 'pilot.py')], pilot)
        shutil.copy2(pilot / 'report.json', output / 'pilot.json')
        shutil.copy2(pilot / 'protocol.json', output / 'pilot-protocol.json')
    except (RuntimeError, OSError) as error:
        # Do not expose machine paths, credentials, or raw subprocess logs.
        results.append({'step': 'runner', 'passed': False, 'reason': type(error).__name__})
    passed = bool(results) and all(x['passed'] for x in results)
    summary = {'schema_version': 1, 'passed': passed, 'steps': results,
               'limits': ['Public tests only; no independent human review or private holdout.']}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    print(f'Local diagnostics (not for publication): {root}')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
