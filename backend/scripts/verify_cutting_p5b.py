"""Repeatable isolated acceptance. Never promotes synthetic results to signoff."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_state():
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT)
    untracked = git('ls-files', '--others', '--exclude-standard', '-z').decode('utf-8').split('\0')
    return {'head':git('rev-parse','HEAD').decode().strip(),
            'tracked_diff_sha256':hashlib.sha256(git('diff','HEAD','--binary')).hexdigest(),
            'untracked':{name:digest(ROOT/name) for name in untracked if name and (ROOT/name).is_file()}}


def junit_summary(path):
    tree = ET.parse(path)
    cases = list(tree.iter('testcase'))
    return {'tests':len(cases),
            'failed':sum(c.find('failure') is not None or c.find('error') is not None for c in cases),
            'skipped':[{'test':c.get('classname','')+'::'+c.get('name',''), 'reason':c.find('skipped').get('message','')}
                       for c in cases if c.find('skipped') is not None]}


def execute_steps(steps, output, env, invoke=subprocess.run):
    results = []
    for name, command, cwd in steps:
        log = output / (name+'.log')
        with log.open('w', encoding='utf-8') as stream:
            try:
                result = invoke(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=1200)
                code = result.returncode
            except KeyboardInterrupt:
                stream.write('Acceptance interrupted; remaining steps were not run.\n')
                code = 130
            except (OSError, subprocess.TimeoutExpired) as error:
                stream.write(str(error))
                code = -1
        results.append({'step':name,'command':command,'cwd':str(cwd),'exit_code':code,'log':log.name})
        if code:
            break
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scope', choices=('core','focused','full'), default='full')
    args = parser.parse_args()
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]
    output = ROOT/'.tmp'/'cutting-p5b'/run
    output.mkdir(parents=True, exist_ok=False)
    report = {'run_id':run,'scope':args.scope,'started_at':datetime.now(timezone.utc).isoformat(),
              'source':source_state(),'python':sys.version,'formal_acceptance':'pending_real_data_and_employee_signoff',
              'browser_acceptance':'pending_separate_browser_record','postgresql_acceptance':'not_run',
              'status':'running','steps':[]}
    report_path = output/'report.json'
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8', DATABASE_URL='sqlite://',
               CUTTING_TEST_POSTGRES_URL='', SEED_DEFAULT_ACCOUNTS='false')
    backend = ROOT/'backend'
    tests = ([str(p.relative_to(backend)) for p in sorted((backend/'tests').glob('test_cutting*.py'))]
             if args.scope=='full' else ['tests/test_cutting_p5b_acceptance.py'])
    if args.scope!='full':
        tests.append('tests/test_cutting_p5b_runner.py')
    xml = output/'backend.xml'
    steps = [('backend',[sys.executable,'-m','pytest',*tests,'-q','-p','no:cacheprovider',
        '--basetemp='+str(output/'databases'),'--junitxml='+str(xml)],backend)]
    # IAM's full-app fixture owns its own fresh SQLite and needs its synthetic
    # administrator. Isolate it from local module flags and cutting module imports.
    identity_xml = output/'identity.xml'
    identity_command = [sys.executable, '-c',
        "import os,runpy,sys; os.environ.update(SEED_DEFAULT_ACCOUNTS='true',CUTTING_OPS_ENABLED='false',ASSISTANT_ENABLED='false',COLLABORATION_ENABLED='false'); sys.argv=['pytest',*sys.argv[1:]]; runpy.run_module('pytest',run_name='__main__')",
        'tests/test_identity_acceptance.py','-q','-x','-p','no:cacheprovider','--junitxml='+str(identity_xml)]
    if args.scope != 'full':
        identity_command += ['-k', 'package_change_preserves_formal_department or freeze_invalidates_every_session or stopped_worker_boundary_all_identity_consumers']
    steps.append(('identity',identity_command,backend))
    if args.scope!='core':
        node = shutil.which('node')
        if not node:
            parser.error('Node.js is required for full acceptance')
        steps += [
            ('frontend',[node,str(ROOT/'node_modules/vitest/vitest.mjs'),'run','src/features/cutting-operations/__tests__','--maxWorkers=2'],ROOT),
            ('test-types',[node,str(ROOT/'node_modules/vue-tsc/bin/vue-tsc.js'),'--noEmit','-p','tsconfig.cutting-tests.json'],ROOT),
            ('build', [shutil.which('cmd.exe') or 'cmd.exe','/d','/c','npm run build'] if os.name=='nt' else ['npm','run','build'],ROOT),
        ]
    print(str(output),flush=True)
    report['steps'] = execute_steps(steps,output,env)
    if xml.exists():
        report['backend'] = junit_summary(xml)
    if identity_xml.exists():
        report['identity'] = junit_summary(identity_xml)
    report['status'] = 'failed' if any(s['exit_code'] for s in report['steps']) else 'passed'
    if report.get('backend',{}).get('failed'):
        report['status'] = 'failed'
    if report.get('backend',{}).get('skipped') and report['status']=='passed':
        report['status'] = 'passed_with_skips'
    # Copy only generated synthetic spreadsheets, not DB files or credentials.
    exports = output/'exports'
    exports.mkdir()
    for i, path in enumerate(sorted((output/'databases').rglob('*.xlsx'))):
        shutil.copyfile(path,exports/f'{i:03d}-{path.name}')
    report['artifacts'] = {str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*'))
                           if p.is_file() and (p.parent==exports or p.suffix in {'.log','.xml'})}
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    report['source_after'] = source_state()
    if report['source_after'] != report['source']:
        report['status'] = 'invalidated_source_changed'
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(report['status'],flush=True)
    return 0 if report['status'] in {'passed','passed_with_skips'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
