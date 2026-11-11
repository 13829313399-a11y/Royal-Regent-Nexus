"""Build an isolated, source-fingerprinted order engine without ERP startup code."""
from __future__ import annotations
import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
TOOL = Path(__file__).resolve().parent
SEEDS = [f'app.services.customer_order_{name}' for name in ('unified', 'buzzbee', 'dickie', 'caixing', 'manual')]
SEEDS += ['app.services.huaxing_order_legacy.order_ocr_worker','app.services.customer_order_casdon',
          'app.services.customer_order_360_workbook','app.services.order_workbook_bounds']
HELPERS = {'_get_mapped_customer_spec', '_create_mapped_customer_preview', '_export_mapped_customer_schedule',
 '_create_special_batch_preview', '_export_special_batch_schedule', '_validate_upload', '_is_macos_metadata_upload',
 '_parse_skipped_issue_keys', '_parse_manual_overrides', '_is_test_duplicate_issue_key',
 '_ensure_test_duplicate_confirmation_allowed', '_apply_customer_order_confirmation_policy',
 '_preview_fingerprint', '_validated_confirmation_reason', '_actual_confirmed_issue_keys',
 '_actual_manual_overrides', '_ensure_preview_fingerprint'}
CONSTANTS = {'MAX_SKIPPED_ISSUE_KEYS','MAX_CONFIRMATION_REASON_LENGTH','MIN_CONFIRMATION_REASON_LENGTH',
 'MAX_MANUAL_OVERRIDES','MAX_MANUAL_OVERRIDE_VALUE_LENGTH','PREVIEW_FINGERPRINT_VERSION','TEST_DUPLICATE_ISSUE_CODES'}
IMPORT_MODULES = {'hashlib','hmac','json','fastapi','app.services.customer_order_buzzbee',
 'app.services.customer_order_dickie','app.services.customer_order_caixing','app.services.customer_order_huaxing',
 'app.services.customer_order_huadeng','app.services.customer_order_huakang_a','app.services.customer_order_huakang_c',
 'app.services.customer_order_manual','app.services.customer_order_unified'}


def module_file(module):
    path=BACKEND.joinpath(*module.split('.')).with_suffix('.py')
    if path.is_file(): return path
    path=BACKEND.joinpath(*module.split('.'), '__init__.py')
    return path if path.is_file() else None


def closure():
    seen=set(); pending=SEEDS.copy()
    while pending:
        name=pending.pop()
        if name in seen: continue
        path=module_file(name)
        if path is None: continue
        seen.add(name)
        for node in ast.walk(ast.parse(path.read_text())):
            imports=[]
            if isinstance(node,ast.Import): imports=[v.name for v in node.names]
            elif isinstance(node,ast.ImportFrom):
                base=node.module or ''
                if node.level:
                    pieces=name.split('.') if path.name=='__init__.py' else name.split('.')[:-1]
                    if node.level>1: pieces=pieces[:-(node.level-1)]
                    base='.'.join(pieces+([base] if base else []))
                imports=[base]+[base+'.'+v.name for v in node.names if v.name!='*']
            pending.extend(value for value in imports if value.startswith('app.') and module_file(value))
    return sorted(module_file(name) for name in seen)


def contract():
    source=BACKEND/'app/api/customer_order.py'; text=source.read_text(); tree=ast.parse(text)
    pieces=['"""Pure controls extracted from the exact recorded ERP source."""',
            'from __future__ import annotations', 'from types import SimpleNamespace',
            '# The standalone trial matches the existing non-production duplicate-confirmation policy.',
            'settings = SimpleNamespace(effective_customer_order_test_duplicate_confirmation_enabled=True)']
    for node in tree.body:
        if isinstance(node,ast.Import) and all(v.name in IMPORT_MODULES for v in node.names): pieces.append(ast.get_source_segment(text,node))
        elif isinstance(node,ast.ImportFrom) and node.module in IMPORT_MODULES: pieces.append(ast.get_source_segment(text,node))
        elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in HELPERS: pieces.append(ast.get_source_segment(text,node))
        elif isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in CONSTANTS for t in node.targets): pieces.append(ast.get_source_segment(text,node))
    return '\n\n'.join(pieces)+'\n'


def build(destination):
    destination=Path(destination).resolve(); destination.mkdir(parents=True,exist_ok=True)
    manifest=[]
    def copy(path, relative=None):
        relative=relative or path.relative_to(BACKEND)
        target=destination/relative; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(path,target)
        manifest.append({'source':str(path.relative_to(ROOT)), 'target':str(relative), 'sha256':sha256(path.read_bytes()).hexdigest(), 'mode':'exact-copy'})
    for path in closure(): copy(path)
    copy(BACKEND/'app/services/customer_order_jobs.py')
    # Ledger state machine and schemas remain byte-identical. Infrastructure is local-only.
    for name in ('app/models/customer_order_ledger.py','app/schemas/customer_order_ledger.py',
                 'app/services/customer_order_ledger.py','app/services/customer_order_queries.py',
                 'app/services/customer_order_history.py','app/services/customer_order_schedule.py'):
        copy(BACKEND/name)
    auth=BACKEND/'app/services/auth.py';auth_text=auth.read_text()
    clock=next(node for node in ast.parse(auth_text).body if isinstance(node,ast.FunctionDef) and node.name=='now_text')
    (destination/'app/services/auth.py').write_text('from datetime import datetime\n\n'+ast.get_source_segment(auth_text,clock)+'\n')
    manifest.append({'source':str(auth.relative_to(ROOT)),'target':'app/services/auth.py','sha256':sha256(auth.read_bytes()).hexdigest(),'mode':'clock-only-AST-extraction','symbols':['now_text']})
    copy(BACKEND/'scripts/convert_excel_workbook.ps1')
    # The original watchdog, resource limits, process tree and private IPC stay intact;
    # only the callable resolver is narrowed to the standalone engine operations.
    source=BACKEND/'app/workers/customer_order_job.py'; raw=source.read_text(); tree=ast.parse(raw)
    compute=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='compute')
    lines=raw.splitlines(keepends=True)
    replacement='''def compute(source):
    from app.services.customer_order_jobs import OPERATIONS
    from app import order_contract
    from app.services import customer_order_history, customer_order_casdon
    from app.services.customer_order_360_workbook import organize_workbook
    with source.open("rb") as stream:
        operation, args, kwargs = pickle.load(stream)
    if operation not in {"_create_special_batch_preview", "_export_special_batch_schedule", "_create_mapped_customer_preview", "_export_mapped_customer_schedule", "parse_workbook", "_casdon_preview", "_casdon_export", "organize_workbook"}:
        raise ValueError("Unsupported standalone order job")
    if operation == "parse_workbook":
        function = customer_order_history.parse_workbook
    elif operation in {"_casdon_preview", "_casdon_export"}:
        function = getattr(customer_order_casdon, operation)
    elif operation == "organize_workbook":
        function = organize_workbook
    else:
        function = getattr(order_contract, operation)
    return function(*args, **kwargs)
'''
    worker=''.join(lines[:compute.lineno-1])+replacement+''.join(lines[compute.end_lineno:])
    target=destination/'app/workers/customer_order_job.py';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(worker)
    manifest.append({'source':str(source.relative_to(ROOT)),'target':'app/workers/customer_order_job.py', 'sha256':sha256(source.read_bytes()).hexdigest(),'mode':'restricted-operation-resolver'})
    contract_path=destination/'app/order_contract.py';contract_path.write_text(contract())
    manifest.append({'source':'backend/app/api/customer_order.py','target':'app/order_contract.py','sha256':sha256((BACKEND/'app/api/customer_order.py').read_bytes()).hexdigest(),'mode':'pure-helper-AST-extraction','symbols':sorted(HELPERS)})
    shutil.copytree(TOOL/'server',destination,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for directory in [destination/'app',destination/'app/workers',destination/'app/schemas',destination/'app/models']:
        (directory/'__init__.py').touch()
    migration=BACKEND/'alembic/versions/20260914_0112_customer_order_ledger.py'
    migration_text=migration.read_text();migration_tree=ast.parse(migration_text)
    immutable=next(node for node in migration_tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='IMMUTABLE' for t in node.targets))
    upgrade=next(node for node in migration_tree.body if isinstance(node,ast.FunctionDef) and node.name=='upgrade')
    sqlite_branch=next(node for node in upgrade.body if isinstance(node,ast.If) and ast.unparse(node.test)=="dialect == 'sqlite'")
    from types import SimpleNamespace
    guard_sql=[]
    exec(compile(ast.Module(body=[immutable,*sqlite_branch.body],type_ignores=[]),str(migration),'exec'),{'op':SimpleNamespace(execute=guard_sql.append)})
    if len(guard_sql)!=14:raise RuntimeError('Unexpected source ledger guard count')
    (destination/'app/ledger-guards.json').write_text(json.dumps(guard_sql,indent=2)+'\n')
    manifest.append({'source':str(migration.relative_to(ROOT)),'target':'app/ledger-guards.json','sha256':sha256(migration.read_bytes()).hexdigest(),'mode':'sqlite-immutable-trigger-AST-extraction'})
    for entry in manifest:
        entry['target_sha256']=sha256((destination/entry['target']).read_bytes()).hexdigest()
    for path in sorted((TOOL/'server').rglob('*')):
        if path.is_file() and path.suffix=='.py' and '__pycache__' not in path.parts:
            relative=path.relative_to(TOOL/'server')
            manifest.append({'source':str(path.relative_to(ROOT)),'target':str(relative),'sha256':sha256(path.read_bytes()).hexdigest(),
                'target_sha256':sha256((destination/relative).read_bytes()).hexdigest(),'mode':'standalone-adapter'})
    revision=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
    (destination/'source-manifest.json').write_text(json.dumps({'source_commit':revision,'files':manifest},ensure_ascii=False,indent=2)+'\n')
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('destination',nargs='?',default=TOOL/'build/python')
    print(build(parser.parse_args().destination))
