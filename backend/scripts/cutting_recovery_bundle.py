"""Local recovery package primitives; configurations are Windows-user protected."""
from contextlib import closing
from hashlib import sha256
from pathlib import Path, PurePosixPath
import ctypes
import json
import os
import shutil
import sqlite3
import stat
from uuid import uuid4


def file_hash(path):
    h=sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def checked_file(root, relative):
    value=PurePosixPath(relative)
    if not relative or value.is_absolute() or any(p in {'.','..'} or ':' in p or '\\' in p for p in value.parts):
        raise ValueError('Unsafe recovery entry')
    result=root.joinpath(*value.parts)
    if not result.resolve().is_relative_to(root.resolve()):raise ValueError('Recovery path escapes its package')
    return result


def reject_link(path):
    info=path.lstat()
    if path.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:
        raise ValueError('Links/reparse points are not accepted in recovery packages')


def inventory(root):
    reject_link(root);result={}
    for path in root.rglob('*'):
        reject_link(path)
        if path.is_file():result[path.relative_to(root).as_posix()]=dict(size=path.stat().st_size,sha256=file_hash(path))
    return result


def copy_tree(source,target, *, code=False):
    reject_link(source);target.mkdir(exist_ok=False)
    for path in source.iterdir():
        reject_link(path)
        if code and (path.name in {'__pycache__','node_modules','.venv','.git','.tmp','dist','.pytest_cache'}
                     or path.name.startswith('.env') or '.local.' in path.name or path.suffix in {'.pyc','.db','.sqlite','.sqlite3'}):continue
        if path.is_dir():copy_tree(path,target/path.name,code=code)
        else:shutil.copy2(path,target/path.name)


def protect_config(data, *, decrypt=False):
    """DPAPI CurrentUser, no UI, no exported key; different target users need a new secret handover."""
    if os.name!='nt':raise RuntimeError('This local rehearsal requires Windows DPAPI; no plaintext fallback')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('length',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    raw=ctypes.create_string_buffer(data);entropy=ctypes.create_string_buffer(b'RRN cutting recovery config v1')
    incoming=Blob(len(data),ctypes.cast(raw,ctypes.POINTER(ctypes.c_ubyte)))
    extra=Blob(len(entropy.raw)-1,ctypes.cast(entropy,ctypes.POINTER(ctypes.c_ubyte)));out=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    fn=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    fn.restype=wintypes.BOOL
    if not fn(ctypes.byref(incoming),None,ctypes.byref(extra),None,None,1,ctypes.byref(out)):
        raise RuntimeError('Protected recovery configuration cannot be processed (DPAPI error '+str(ctypes.get_last_error())+')')
    free=ctypes.WinDLL('kernel32').LocalFree;free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p
    try:return ctypes.string_at(out.data,out.length)
    finally:free(ctypes.cast(out.data,ctypes.c_void_p))


def create_bundle(database, source, storage, settings, metadata, bundle, *, protect=protect_config):
    # Caller has already fenced the proven synthetic fixture and new owned path.
    bundle.mkdir(exist_ok=False)
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(bundle/'database.db')) as dst:src.backup(dst)
    copy_tree(source,bundle/'source',code=True)
    if storage.exists():copy_tree(storage,bundle/'storage')
    else:(bundle/'storage').mkdir()
    (bundle/'synthetic-fixtures').mkdir()
    (bundle/'synthetic-fixtures/binary-proof.bin').write_bytes(b'RRN SYNTHETIC RECOVERY ONLY\x00\xff\x01')
    (bundle/'synthetic-fixtures/reference.json').write_text('{"kind":"synthetic-recovery-sentinel","business_attachment":false}',encoding='utf-8')
    protected=dict(settings=settings,release=metadata,files=inventory(bundle))
    (bundle/'configuration.dpapi').write_bytes(protect(json.dumps(protected,ensure_ascii=False).encode()))
    record=dict(kind='cutting-synthetic-recovery-v1',release=metadata,files=inventory(bundle),configuration_protection='Windows DPAPI CurrentUser')
    (bundle/'bundle.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return record


def validate_bundle(bundle):
    reject_link(bundle)
    marker=bundle/'bundle.json';reject_link(marker)
    value=json.loads(marker.read_text(encoding='utf-8'))
    if value.get('kind')!='cutting-synthetic-recovery-v1':raise ValueError('Unexpected recovery package')
    for name in value['files']:
        path=checked_file(bundle,name);reject_link(path)
    actual=inventory(bundle);actual.pop('bundle.json')
    if actual!=value['files']:raise ValueError('Recovery package integrity check failed before restoration')
    return value


def restore_bundle(bundle, database_folder, release_folder, *, unprotect=lambda value:protect_config(value,decrypt=True),owner_token=None):
    value=validate_bundle(bundle)
    protected=json.loads(unprotect((bundle/'configuration.dpapi').read_bytes()))
    files=dict(value['files']);files.pop('configuration.dpapi')
    if protected['files']!=files or protected['release']!=value['release']:
        raise ValueError('Recovery manifest differs from its protected binding')
    settings=protected['settings']
    if settings.get('SEED_DEFAULT_ACCOUNTS')!='false':raise ValueError('Recovery must not seed default accounts')
    if database_folder.exists() or release_folder.exists():raise ValueError('Never overwrite an existing recovery target')
    database_folder.mkdir();release_folder.mkdir()
    (release_folder/'.recovery-owner').write_text(owner_token or uuid4().hex,encoding='ascii')
    target=database_folder/'cutting.db';shutil.copy2(bundle/'database.db',target)
    copy_tree(bundle/'storage',database_folder/'storage')
    copy_tree(bundle/'synthetic-fixtures',database_folder/'synthetic-fixtures')
    copy_tree(bundle/'source',release_folder/'source')
    # Only this private runtime file is temporarily plaintext, like the existing
    # launcher; the retained package remains DPAPI encrypted. Caller removes it.
    settings['DATABASE_URL']='sqlite:///'+target.as_posix();settings['PYTHONPATH']=''
    for key in ['ASSISTANT_STORAGE_DIR','COLLABORATION_STORAGE_DIR','DOCUMENT_TOOLS_STORAGE_DIR','THREE_D_ASSET_DIR']:
        settings[key]=(database_folder/'storage'/key.lower()).as_posix()
    config=release_folder/'environment.local.json'
    config.write_text(json.dumps(settings,ensure_ascii=False),encoding='utf-8')
    manifest=dict(value['release'],release=str(release_folder),source=str(release_folder/'source'),release_ready=False)
    path=release_folder/'manifest.json';path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (database_folder/'fixture.json').write_text(json.dumps(dict(kind='cutting-full-app-synthetic',database=str(target.resolve()),manifest=str(path.resolve()),manifest_sha256=file_hash(path))),encoding='utf-8')
    if file_hash(target)!=file_hash(bundle/'database.db'):raise ValueError('Restored database bytes differ')
    if inventory(release_folder/'source')!={k.removeprefix('source/'):v for k,v in value['files'].items() if k.startswith('source/')}:
        raise ValueError('Restored source differs from its protected file inventory')
    if inventory(database_folder/'storage')!={k.removeprefix('storage/'):v for k,v in value['files'].items() if k.startswith('storage/')}:
        raise ValueError('Restored storage differs')
    if inventory(database_folder/'synthetic-fixtures')!={k.removeprefix('synthetic-fixtures/'):v for k,v in value['files'].items() if k.startswith('synthetic-fixtures/')}:
        raise ValueError('Synthetic nonempty binary proof differs')
    return target,manifest


def cleanup_runtime_config(release,owner_token):
    """Never delete a preexisting target's configuration, even on early failure."""
    marker=release/'.recovery-owner'
    if not marker.is_file():return False
    reject_link(release);reject_link(marker)
    if marker.read_text(encoding='ascii')!=owner_token:return False
    config=release/'environment.local.json'
    if config.is_file():config.unlink()
    return not config.exists()


def finalize_cleanup(release,owner_token,report):
    try:
        removed=cleanup_runtime_config(release,owner_token)
    except (OSError,ValueError) as error:
        report.update(status='failed',plaintext_runtime_config_removed=False,cleanup_error_type=type(error).__name__)
        return error
    report['plaintext_runtime_config_removed']=removed
    if not removed and report.get('status')=='passed':
        report.update(status='failed',cleanup_error_type='MissingOwnedConfigurationProof')
        return RuntimeError('Owned runtime configuration cleanup was not verified')
    return None
