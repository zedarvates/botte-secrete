import importlib.metadata as md
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

root = Path.cwd()
env = os.environ.copy()
for key in ('PYTHONPATH', 'PYTHONHOME'):
    env.pop(key, None)
home = root / 'isolated-home'
home.mkdir(exist_ok=True)
env.update(HOME=str(home), USERPROFILE=str(home), BOTTE_NN_AUTO_LABELS='0',
           PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
report = {'platform': platform.platform(), 'python': sys.version, 'checks': []}

def run(name, args, input_text=None):
    try:
        r = subprocess.run(args, cwd=root, env=env, input=input_text,
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=90)
        (root / (name + '.log')).write_text(r.stdout + '\nSTDERR:\n' + r.stderr, encoding='utf-8')
        report['checks'].append({'name': name, 'exit': r.returncode, 'passed': r.returncode == 0})
        return r
    except subprocess.TimeoutExpired:
        report['checks'].append({'name': name, 'passed': False, 'reason': 'timeout'})

import skills
dist = md.distribution('botte-secrete')
direct = json.loads(dist.read_text('direct_url.json'))
source_ok = (direct.get('vcs_info', {}).get('commit_id') ==
             'd98505fd6586ff3d0d32a2cb4ebd5f0408d4142a' or
             direct.get('archive_info', {}).get('hashes', {}).get('sha256') ==
             '49ffa989764b26a2a8ee96d19085acb256b49363e43aedd3f51a290283b01f42')
report.update(version=dist.version, module_version=skills.__version__, source=direct)
report['checks'].append({'name': 'installed_identity', 'passed':
    dist.version == skills.__version__ == '2.0.0rc1' and
    source_ok and
    Path(skills.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())})
bindir = Path(sys.executable).parent
exe = '.exe' if os.name == 'nt' else ''
run('pip-check', [sys.executable, '-m', 'pip', 'check'])
run('cli-help', [str(bindir / ('botte' + exe)), '--help'])
run('cli-belt', [str(bindir / ('botte' + exe)), 'belt'])
for module in ('test_factory_assurance', 'test_integrations', 'test_roles'):
    run(module, [sys.executable, '-m', 'skills.factory_assurance.' + module])
requests = [
    {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'isolated-smoke','version':'1'}}},
    {'jsonrpc':'2.0','method':'notifications/initialized'},
    {'jsonrpc':'2.0','id':2,'method':'tools/list'},
    {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'find_tool','arguments':{'query':'assurance','top_k':3}}},
    {'jsonrpc':'2.0','id':4,'method':'ping'},
]
r = run('mcp-stdio', [str(bindir / ('botte-mcp' + exe))], ''.join(json.dumps(x)+'\n' for x in requests))
try:
    replies = {x['id']:x for x in map(json.loads, r.stdout.splitlines())}
    assert set(replies) == {1,2,3,4}
    assert all('result' in x and not x['result'].get('isError') for x in replies.values())
    assert replies[1]['result']['serverInfo'] and replies[2]['result']['tools']
    report['mcp_tool_count'] = len(replies[2]['result']['tools'])
    report['checks'].append({'name':'mcp_protocol', 'passed':True})
except Exception as e:
    report['checks'].append({'name':'mcp_protocol', 'passed':False, 'reason':type(e).__name__})
report['passed'] = all(x['passed'] for x in report['checks'])
(root / 'smoke-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
raise SystemExit(0 if report['passed'] else 1)
