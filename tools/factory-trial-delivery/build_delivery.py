"""Assemble self-contained Windows trial ZIPs from reviewed local build outputs."""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from email.parser import Parser
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED
from zoneinfo import ZoneInfo

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

ROOT = Path(__file__).resolve().parents[2]
TOOL = Path(__file__).resolve().parent
FACTORIES = {
    'huakang-a': ('01_华康A_订单排期', 'HuakangA_Trial', '华康A', '360、Green Toys、HeadStart'),
    'huakang-b': ('02_华康B_JP问单', 'HuakangB_JP_Trial', '华康B', 'JP问单录入、44列金山格式导出'),
    'huakang-d': ('03_华康D_订单排期', 'HuakangD_Trial', '华康D', 'INDEX、JAZAWARES、MAXX、STROTTMAN、优必选、迪士尼、施信'),
    'huaxing': ('04_华兴_订单排期', 'Huaxing_Trial', '华兴', 'ZURU、BuzzBee、Dickie、彩星、EDU、360、银辉、施信、Maxx、Shushupapa、Barter、迪士尼'),
    'huadeng': ('05_华登_订单排期', 'Huadeng_Trial', '华登', 'Goliath、Casdon、Jakks、Simba、Spin'),
}
START = ('@echo off\r\nchcp 65001 >nul\r\nsetlocal\r\ncd /d "%~dp0"\r\n'
         '"runtime\\python.exe" -X utf8 launch.py\r\nif errorlevel 1 pause\r\n')


def safe_archive_name(name: str):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '\\' in name or '..' in path.parts or name.rstrip('/') != path.as_posix():
        raise ValueError(f'Unsafe archive entry: {name}')
    for part in path.parts:
        if (re.search(r'[\x00-\x1f<>:"|?*]', part) or part.endswith((' ', '.'))
                or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part)):
            raise ValueError(f'Unsafe Windows archive entry: {name}')
    return path


def extract(archive: Path, destination: Path):
    with ZipFile(archive) as zipped:
        seen = set()
        # Validate the whole directory before writing any entry, including Unix
        # symlink metadata and paths that collide on case-insensitive Windows.
        for entry in zipped.infolist():
            path = safe_archive_name(entry.orig_filename)
            key = path.as_posix().casefold()
            if stat.S_ISLNK(entry.external_attr >> 16) or key in seen:
                raise ValueError(f'Unsafe archive entry: {entry.filename}')
            seen.add(key)
            target = destination / path
            if not target.resolve().is_relative_to(destination.resolve()) or target.is_symlink():
                raise ValueError(f'Archive entry leaves destination: {entry.filename}')
            if target.exists() and not (entry.is_dir() and target.is_dir()):
                raise ValueError(f'Archive entry overwrites another package: {entry.filename}')
        for entry in zipped.infolist():
            zipped.extract(entry, destination)


def dependency_inventory(cache: Path):
    pins = {}
    for line in (TOOL / 'requirements-windows.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        requirement = Requirement(line)
        specs = list(requirement.specifier)
        if requirement.marker or requirement.extras or requirement.url or len(specs) != 1 or specs[0].operator != '==':
            raise ValueError(f'Dependency must be an exact unconditional pin: {line}')
        name = canonicalize_name(requirement.name)
        if name in pins:
            raise ValueError(f'Duplicate dependency pin: {name}')
        pins[name] = specs[0].version
    supported = set(cpython_tags((3, 12), abis=['cp312'], platforms=['win_amd64']))
    supported.update(compatible_tags((3, 12), interpreter='cp312', platforms=['win_amd64']))
    environment = default_environment()
    environment.update(os_name='nt', sys_platform='win32', platform_system='Windows', platform_machine='AMD64',
        python_version='3.12', python_full_version='3.12.10', implementation_name='cpython',
        implementation_version='3.12.10', platform_python_implementation='CPython', extra='')
    records, metadata_by_name = [], {}
    for wheel in sorted((cache / 'wheels-pinned').glob('*.whl')):
        name, version, _, tags = parse_wheel_filename(wheel.name)
        if not supported.intersection(tags):
            raise ValueError(f'Wheel is not compatible with CPython 3.12 Windows x64: {wheel.name}')
        if name not in pins or str(version) != pins[name] or name in metadata_by_name:
            raise ValueError(f'Unexpected, duplicate or wrong-version wheel: {wheel.name}')
        with ZipFile(wheel) as zipped:
            entries = [item for item in zipped.namelist() if item.endswith('.dist-info/METADATA')]
            if len(entries) != 1:
                raise ValueError(f'Wheel has ambiguous metadata: {wheel.name}')
            metadata = Parser().parsestr(zipped.read(entries[0]).decode('utf-8'))
            for path in zipped.namelist():
                if '.data/' in path and '.data/scripts/' not in path:
                    raise ValueError(f'Wheel requires an unsupported installation relocation: {path}')
        if canonicalize_name(metadata['Name']) != name or metadata['Version'] != pins[name]:
            raise ValueError(f'Wheel filename and metadata disagree: {wheel.name}')
        if metadata['Requires-Python'] and '3.12.10' not in SpecifierSet(metadata['Requires-Python']):
            raise ValueError(f'Wheel requires another Python version: {wheel.name}')
        metadata_by_name[name] = metadata
        records.append({'name': metadata['Name'], 'version': metadata['Version'], 'wheel': wheel.name,
            'sha256': sha256(wheel.read_bytes()).hexdigest()})
    missing = pins.keys() - metadata_by_name.keys()
    if missing or not pins:
        raise ValueError('Missing pinned Windows dependencies: ' + ', '.join(sorted(missing)))
    for name, metadata in metadata_by_name.items():
        for raw in metadata.get_all('Requires-Dist', []):
            dependency = Requirement(raw)
            if dependency.marker and not dependency.marker.evaluate(environment):
                continue
            selected = pins.get(canonicalize_name(dependency.name))
            if dependency.url or selected is None or selected not in dependency.specifier:
                raise ValueError(f'Unsatisfied Windows dependency of {name}: {raw}')
    return records


def verify_native_sources(cache: Path):
    sources = json.loads((TOOL / 'runtime-sources.json').read_text(encoding='utf-8'))
    for section in ('native_downloads', 'ocr_languages'):
        for record in sources[section]:
            path = cache / record['name'] if section == 'native_downloads' else cache / 'tesseract-extracted/tessdata' / record['name']
            if not path.is_file() or path.is_symlink() or sha256(path.read_bytes()).hexdigest() != record['sha256']:
                raise ValueError(f'Native runtime/model checksum mismatch: {record["name"]}')
    return sources


def runtime(cache: Path, destination: Path):
    verify_native_sources(cache)
    records = dependency_inventory(cache)
    archive = cache / 'python-3.12.10-embed-amd64.zip'
    expected = '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'
    if sha256(archive.read_bytes()).hexdigest() != expected:
        raise ValueError('Python runtime checksum mismatch')
    destination.mkdir(parents=True)
    extract(archive, destination)
    packages = destination / 'Lib' / 'site-packages'
    packages.mkdir(parents=True)
    for record in records:
        wheel = cache / 'wheels-pinned' / record['wheel']
        extract(wheel, packages)
    (destination / 'python312._pth').write_text(
        'python312.zip\n.\nLib/site-packages\n../backend\nimport site\n', encoding='utf-8')
    return records


def copy_tree(source: Path, target: Path):
    if source.is_symlink() or any(path.is_symlink() for path in source.rglob('*')):
        raise ValueError(f'Symbolic links are not delivery inputs: {source.name}')
    shutil.copytree(source, target)


def package_hashes(package: Path):
    hashes, names = [], set()
    for item in sorted(package.rglob('*')):
        relative = item.relative_to(package).as_posix()
        safe_archive_name(relative)
        windows_path = 'D:\\RRTrial\\' + package.name + '\\' + relative.replace('/', '\\')
        if len(windows_path.encode('utf-16-le')) // 2 > 259:
            raise ValueError(f'Delivery path exceeds traditional Windows MAX_PATH under D:\\RRTrial: {relative}')
        if (item.is_symlink() or item.relative_to(package).parts[0] == 'data'
                or any(part in {'.git', '__pycache__', 'node_modules'} for part in item.relative_to(package).parts)
                or item.name.lower().startswith('.env') or item.suffix.lower() in {'.pyc', '.pyo', '.pem', '.key', '.p12', '.pfx'}
                or re.search(r'\.(db|sqlite3?)(-(wal|shm|journal))?$', item.name, re.I)):
            raise ValueError(f'Forbidden delivery artifact: {relative}')
        key = relative.casefold()
        if key in names:
            raise ValueError(f'Case-colliding Windows delivery path: {relative}')
        names.add(key)
        if item.is_file():
            hashes.append({'path': relative, 'sha256': sha256(item.read_bytes()).hexdigest(), 'bytes': item.stat().st_size})
    return hashes


def build_provenance(source: Path, package: Path, source_commit: str):
    manifest = json.loads((package / 'backend/source-manifest.json').read_text(encoding='utf-8'))
    entries = manifest.get('files', manifest.get('unchanged_business_sources', []) + manifest.get('standalone_adapters', []))
    for entry in entries:
        target = package / 'backend' / safe_archive_name(entry['target'])
        expected = entry.get('target_sha256', entry['sha256'])
        if sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Backend source manifest mismatch: {entry["target"]}')
    inputs = []
    for directory in (TOOL, source):
        for parent, directories, files in os.walk(directory):
            directories[:] = sorted(name for name in directories if name not in {'build', 'node_modules', '__pycache__', '.git', '.pytest_cache', 'dist'})
            for filename in sorted(files):
                path = Path(parent) / filename
                if path.suffix not in {'.py', '.ts', '.js', '.vue', '.json', '.html', '.css', '.txt', '.md'}:
                    continue
                if path.is_symlink() or filename.startswith('.env'):
                    raise ValueError(f'Forbidden build input: {path.relative_to(ROOT)}')
                inputs.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': sha256(path.read_bytes()).hexdigest()})
    changed = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT, text=True))
    return {'base_commit': source_commit, 'working_tree_has_changes': changed,
        'commit_meaning': 'Base checkout only. The standalone adapters and build inputs may be uncommitted; their exact hashes are recorded here and in backend/source-manifest.json.',
        'build_inputs': inputs}


def readme(factory: str, release: str):
    _, _, name, customers = FACTORIES[factory]
    common = f'''{name} 单机试用版｜{release}

适用：Windows 10/11 64位电脑。已带 Python 运行文件，不需安装 Python、Node 或登录总系统。

启动
1. 将整个 ZIP 解压到本机短路径，例如 D:\\RRTrial。不要在压缩包预览窗口里直接运行。
2. 双击 START.cmd。页面会在默认浏览器打开；控制台也会显示浏览器地址。
3. 试用时保持控制台打开；结束按 Ctrl+C。重复双击会尝试打开同一个已启动页面。

当前客户／功能：{customers}

数据与交接
- data 文件夹在首次启动时创建，存放本包自己的历史、原件与记录。退出后保留。
- 不连接线上数据库或其他厂区。复制到另一台电脑后是另一套独立数据。
- 备份请先退出程序，再复制整个解压文件夹。更新时将同厂区旧包的 data 复制到新包后再启动；不要混用不同厂区的数据。
- 演示资料仅用于测试。开始真实资料试用时请保留一份未使用的新解压包。
- 上传的是原件副本，下载会生成新 Excel，不会覆盖原文件。
- 反馈问题时请注明厂区、客户、按钮、提示原文，并附可授权核对的原件；启动异常可附 data/startup-error.log。

验证说明
已验证本地API、业务规则、构建和回归；交付前没有在Windows实机或金山桌面应用中验收。
请负责人先完成演示资料流程，再用真实样本逐项核对金额、数量、交期和版式。
'''
    if factory == 'huakang-b':
        common += '''
华康B使用顺序
1. 排期参照、货价表均可选；有参照时可匹配历史和价格，无参照也能解析生成。没有历史编号依据时编号留空，不会擅自从首号开始。
2. 上传 EML、邮件ZIP，或从邮件中直接复制正文表格粘贴；同一封邮件通常选一种方式。填写来单日期和金山人员名称对应的业务跟单。
3. 解析后查看明细。缺资料、候选价格和未识别来源只作提醒；本次生成已识别且选中的明细，缺值留空。改客名或装箱数后旧价清空，可之后补充。
4. 点击“生成问单Excel”直接生成44列文件，无需核对勾选或填写原因。文件保持待核对状态；生成不表示已经核准价格。
5. 已生成记录可下载原Excel，也可“复制全部44列”粘贴到Excel，不含表头；重复下载或复制不重新占号。剪贴板被限制时，按页面提示选中只读内容手动复制。

这是问单工具，不包含PO入正式排期入口。编号仅在本包数据中延续，不与线上或其他电脑共用。
试用编号不能直接作为多人共同使用的正式编号。
'''
    else:
        common += '''
订单／排期使用顺序
1. 选择本厂客户、上传客户PO与对应原排期，填写来单日期后解析。
2. 在预览中逐项核对。“资料待补”可先留空保存或生成排期；人工补录及允许确认的异常须填写原因。订单号、货号、有效数量和原单冲突仍须核对。
3. “保存订单”写入本机台账；“生成排期”下载完整排期副本。这是两个独立操作。
4. 缺货期可先入台账，补齐并保存货期后才能发送到本机部门收件箱；可登记分批走货，走货撤回须保留原因。
5. 本机发送记录不是发给线上员工的通知，也不会更新正式仓库、库存或生产任务。

已随包提供英文／简体中文 OCR 运行文件。扫描件的识别结果仍须核对。
少数旧 .xls 文件的保格式转换调用本机 Microsoft Excel；普通 .xlsx 不需要该转换。
本包不代替正式生产系统；本地发送、签收、走货记录需负责人核对流程后再决定正式上线方式。
'''
    return common


def build(cache: Path, output: Path, selected, release_date: str | None = None):
    release_day = date.fromisoformat(release_date) if release_date else datetime.now(ZoneInfo("Asia/Shanghai")).date()
    release = release_day.isoformat()
    stamp = release_day.strftime("%Y%m%d")
    output.mkdir(parents=True, exist_ok=True)
    source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    records = []
    with tempfile.TemporaryDirectory(prefix='factory-trial-delivery-', dir=cache) as temporary:
        staging = Path(temporary)
        shared_runtime = staging / 'runtime'
        dependencies = runtime(cache, shared_runtime)
        for factory in selected:
            zip_name, folder, name, customers = FACTORIES[factory]
            kind = 'jp' if factory == 'huakang-b' else 'orders'
            source = ROOT / 'tools' / ('huakang-b-jp-trial' if kind == 'jp' else 'customer-order-trial')
            package = staging / folder
            package.mkdir()
            subprocess.run([sys.executable, '-B', str(source / 'prepare_backend.py'), str(package / 'backend')], check=True)
            web = source / 'build' / 'web'
            if not (web / 'index.html').is_file():
                raise RuntimeError(f'Missing built frontend: {web}')
            copy_tree(web, package / 'web')
            copy_tree(shared_runtime, package / 'runtime')
            shutil.copyfile(TOOL / 'launch.py', package / 'launch.py')
            (package / 'START.cmd').write_bytes(START.encode('ascii'))
            (package / '先看使用说明.txt').write_text(readme(factory, release), encoding='utf-8-sig')
            (package / 'trial.json').write_text(json.dumps({'kind': kind, 'factory_id': factory,
                'name': f'{name}问单本地试用' if kind == 'jp' else f'{name}订单排期本地试用',
                'release': release, 'source_commit': source_commit,
                'source_commit_role': 'Base checkout; see BUILD-SOURCES.json for exact uncommitted build inputs.'}, ensure_ascii=False, indent=2), encoding='utf-8')
            if kind == 'orders':
                ocr = package / 'ocr'
                ocr.mkdir()
                native = cache / 'tesseract-extracted'
                for item in native.iterdir():
                    if item.suffix.lower() == '.dll' or item.name == 'tesseract.exe':
                        if item.is_symlink():
                            raise ValueError('OCR runtime cannot contain symbolic links')
                        shutil.copyfile(item, ocr / item.name)
                for directory in ('doc', 'tessdata'):
                    copy_tree(native / directory, ocr / directory)
                if not (ocr / 'tesseract.exe').is_file():
                    raise RuntimeError('Missing OCR executable')
                for lang in ('eng', 'chi_sim'):
                    if not (ocr / 'tessdata' / f'{lang}.traineddata').is_file():
                        raise RuntimeError('Missing OCR language model')
            demo_script = source / 'create_demo.py'
            if demo_script.is_file():
                command = [sys.executable, '-B', str(demo_script), str(package / '演示资料')]
                if kind == 'orders':
                    command += ['--factory', factory]
                subprocess.run(command, check=True)
            (package / 'DEPENDENCIES.json').write_text(json.dumps(dependencies, indent=2), encoding='utf-8')
            for filename in ('runtime-sources.json', 'requirements-windows.txt'):
                shutil.copyfile(TOOL / filename, package / filename)
            provenance = build_provenance(source, package, source_commit)
            (package / 'BUILD-SOURCES.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
            hashes = package_hashes(package)
            (package / 'PACKAGE-MANIFEST.json').write_text(json.dumps({'factory_id': factory,
                'source_commit': source_commit, 'source_commit_role': provenance['commit_meaning'],
                'working_tree_has_changes': provenance['working_tree_has_changes'], 'files': hashes}, ensure_ascii=False, indent=2), encoding='utf-8')
            destination = output / f'{zip_name}_Windows试用_{stamp}.zip'
            partial = destination.with_suffix('.zip.part')
            with ZipFile(partial, 'w', compression=ZIP_DEFLATED, compresslevel=6) as archive:
                for item in sorted(package.rglob('*')):
                    if item.is_file():
                        archive.write(item, str(item.relative_to(staging)))
            partial.replace(destination)
            records.append({'factory_id': factory, 'file': destination.name, 'bytes': destination.stat().st_size,
                'sha256': sha256(destination.read_bytes()).hexdigest(), 'customers': customers})
            print(json.dumps(records[-1], ensure_ascii=False), flush=True)
    (output / '交付文件校验.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / '06_华康C_当前状态说明.txt').write_text('华康C当前没有开放的普通客户订单／排期入口。\n'
        '本次没有生成会重新开放隐藏或历史客户映射的试用程序。\n华康C裁床/BOM/生产模块不在本次订单问单试用范围。\n', encoding='utf-8-sig')
    with (output / '00_交接登记.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['厂区', '试用包', '客户／功能', '对接人', '交付日期', '启动结果', '试用问题'])
        for factory in selected:
            filename, _, name, customers = FACTORIES[factory]
            writer.writerow([name, f'{filename}_Windows试用_{stamp}.zip', customers, '', '', '', ''])
    (output / '00_总说明_先看这里.txt').write_text('各厂区订单／排期与华康B问单｜Windows单机试用包\n\n'
        + '本文件夹包含：' + '、'.join(FACTORIES[key][2] for key in selected) + '。\n' +
        '每个ZIP都是独立包，请把对应厂区的ZIP交给负责人，完整解压后双击START.cmd。\n'
        '不需要总系统账号。仅适用于Windows 10/11 64位。\n'
        '功能范围：华康B只保留JP问单；订单包包含本地订单台账、发送收件、分批走货和排期生成。\n'
        '数据保存在各自解压目录的data中，互不共享，不写入线上系统。\n'
        '发票不在本次范围；华康C当前无普通订单入口，另附状态说明。\n'
        '00_交接登记.csv可填写负责人及反馈。各包内有详细使用说明。\n'
        'Windows实机和金山导入尚需对接人现场试用核对；本地API/业务回归与构建验证见交付验证说明。\n', encoding='utf-8-sig')
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--factory', action='append', choices=FACTORIES)
    parser.add_argument('--release-date', help='Release date YYYY-MM-DD; defaults to the Shanghai calendar date.')
    args = parser.parse_args()
    build(args.cache.resolve(), args.output.resolve(), args.factory or list(FACTORIES), args.release_date)
