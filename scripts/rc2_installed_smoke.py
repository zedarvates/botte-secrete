"""Run with python -I after wheel installation, outside source imports."""
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import skills

assert metadata.version('botte-secrete') == skills.__version__ == '2.0.0rc2'
assert Path(skills.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
env = os.environ.copy()
env.pop('PYTHONPATH', None)
env.pop('PYTHONHOME', None)
env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', BOTTE_NN_AUTO_LABELS='0')
bindir = Path(sysconfig.get_path('scripts'))
suffix = '.exe' if os.name == 'nt' else ''
commands = [[sys.executable, '-m', 'pip', 'check'],
    [str(bindir / ('botte' + suffix)), '--help'],
    [str(bindir / ('botte' + suffix)), 'belt'],
    *[[sys.executable, '-m', 'skills.factory_assurance.' + test]
      for test in ('test_factory_assurance', 'test_integrations', 'test_roles')],
    [sys.executable, '-m', 'skills.response_cache.test_exact']]
with tempfile.TemporaryDirectory(prefix='rc2-smoke-') as directory:
    env.update(HOME=directory, USERPROFILE=directory)
    for command in commands:
        subprocess.run(command, cwd=directory, env=env, check=True, timeout=90)
    requests = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2024-11-05', 'capabilities': {},
            'clientInfo': {'name': 'rc2-smoke', 'version': '1'}}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'ping'}]
    response = subprocess.run([str(bindir / ('botte-mcp' + suffix))],
        input=''.join(json.dumps(r)+'\n' for r in requests), text=True,
        encoding='utf-8', capture_output=True, cwd=directory, env=env,
        check=True, timeout=30)
    replies = {r['id']: r for r in map(json.loads, response.stdout.splitlines())}
    assert set(replies) == {1, 2, 3}
    assert all('result' in r for r in replies.values())
    assert replies[2]['result']['tools']
print('RC2 installed wheel: CLI, MCP, dependencies, assurance, exact cache passed')
