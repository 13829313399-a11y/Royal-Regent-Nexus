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
    'huakang-a': ('01_华康A_订单排期', 'HuakangA_Trial', '华康A', 'ZURU、360、Green Toys、HeadStart'),
    'huakang-b': ('02_华康B_JP问单', 'HuakangB_JP_Trial', '华康B', 'JP问单录入、44列金山格式导出'),
    'huakang-d': ('03_华康D_订单排期', 'HuakangD_Trial', '华康D', 'INDEX、JAZAWARES、MAXX、STROTTMAN、优必选、迪士尼、施信'),
    'huaxing': ('04_华兴_订单排期', 'Huaxing_Trial', '华兴', 'ZURU、BuzzBee、Dickie、彩星、EDU、360、银辉、施信、Maxx、Shushupapa、Barter、迪士尼'),
    'huadeng': ('05_华登_订单排期', 'Huadeng_Trial', '华登', 'Goliath、Casdon、Jakks、Simba、Spin'),
}
START = (TOOL / 'start.cmd').read_text(encoding='ascii').replace('\n', '\r\n')
SINGLE_CUSTOMERS = {'casdon': ('huadeng', 'Casdon'), 'jakks': ('huadeng', 'Jakks'),
    'goliath': ('huadeng', 'Goliath'), 'simba': ('huadeng', 'Simba'),
    'spin': ('huadeng', 'Spin'), 'zuru': ('huakang-a', 'ZURU')}


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


def dependency_inventory(cache: Path, legacy=False):
    pins = {}
    for line in (TOOL / ('requirements-win7.txt' if legacy else 'requirements-windows.txt')).read_text(encoding='utf-8').splitlines():
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
    version, abi, platform = ((3, 8), 'cp38', 'win32') if legacy else ((3, 12), 'cp312', 'win_amd64')
    supported = set(cpython_tags(version, abis=[abi], platforms=[platform]))
    supported.update(compatible_tags(version, interpreter=abi, platforms=[platform]))
    environment = default_environment()
    environment.update(os_name='nt', sys_platform='win32', platform_system='Windows', platform_machine='AMD64',
        python_version='3.12', python_full_version='3.12.10', implementation_name='cpython',
        implementation_version='3.12.10', platform_python_implementation='CPython', extra='')
    if legacy:
        environment.update(platform_machine='x86', python_version='3.8', python_full_version='3.8.10', implementation_version='3.8.10')
    records, metadata_by_name = [], {}
    for wheel in sorted((cache / 'wheels-pinned').glob('*.whl')):
        name, version, _, tags = parse_wheel_filename(wheel.name)
        if not supported.intersection(tags):
            raise ValueError(f'Wheel is not compatible with {abi} {platform}: {wheel.name}')
        if name not in pins or str(version) != pins[name] or name in metadata_by_name:
            raise ValueError(f'Unexpected, duplicate or wrong-version wheel: {wheel.name}')
        with ZipFile(wheel) as zipped:
            entries = [item for item in zipped.namelist() if item.endswith('.dist-info/METADATA')]
            if len(entries) != 1:
                raise ValueError(f'Wheel has ambiguous metadata: {wheel.name}')
            metadata = Parser().parsestr(zipped.read(entries[0]).decode('utf-8'))
            for path in zipped.namelist():
                if '.data/' in path and '.data/scripts/' not in path and '.data/headers/' not in path:
                    raise ValueError(f'Wheel requires an unsupported installation relocation: {path}')
        if canonicalize_name(metadata['Name']) != name or metadata['Version'] != pins[name]:
            raise ValueError(f'Wheel filename and metadata disagree: {wheel.name}')
        if metadata['Requires-Python'] and environment['python_full_version'] not in SpecifierSet(metadata['Requires-Python']):
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


def verify_native_sources(cache: Path, legacy=False):
    sources = json.loads((TOOL / ('runtime-sources-win7.json' if legacy else 'runtime-sources.json')).read_text(encoding='utf-8'))
    for section in ('native_downloads', 'ocr_languages'):
        for record in sources[section]:
            path = cache / record['name'] if section == 'native_downloads' else cache / 'tesseract-extracted/tessdata' / record['name']
            if not path.is_file() or path.is_symlink() or sha256(path.read_bytes()).hexdigest() != record['sha256']:
                raise ValueError(f'Native runtime/model checksum mismatch: {record["name"]}')
    return sources


def runtime(cache: Path, destination: Path, legacy=False):
    native = verify_native_sources(cache, legacy)
    records = dependency_inventory(cache, legacy)
    selected = next(record for record in native['native_downloads'] if record['name'].startswith('python-'))
    archive = cache / selected['name']
    expected = selected['sha256']
    if sha256(archive.read_bytes()).hexdigest() != expected:
        raise ValueError('Python runtime checksum mismatch')
    destination.mkdir(parents=True)
    extract(archive, destination)
    packages = destination / 'Lib' / 'site-packages'
    packages.mkdir(parents=True)
    for record in records:
        wheel = cache / 'wheels-pinned' / record['wheel']
        extract(wheel, packages)
    stdlib = 'python38' if legacy else 'python312'
    (destination / (stdlib + '._pth')).write_text(
        stdlib + '.zip\n.\nLib/site-packages\n../backend\nimport site\n', encoding='utf-8')
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
                if path.suffix not in {'.py', '.ts', '.js', '.vue', '.json', '.html', '.css', '.txt', '.md', '.cmd'}:
                    continue
                if path.is_symlink() or filename.startswith('.env'):
                    raise ValueError(f'Forbidden build input: {path.relative_to(ROOT)}')
                inputs.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': sha256(path.read_bytes()).hexdigest()})
    changed = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT, text=True))
    return {'base_commit': source_commit, 'working_tree_has_changes': changed,
        'commit_meaning': 'Base checkout only. The standalone adapters and build inputs may be uncommitted; their exact hashes are recorded here and in backend/source-manifest.json.',
        'build_inputs': inputs}


def readme(factory: str, release: str, green_toys_only: bool = False):
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
- 反馈问题时请注明厂区、客户、按钮、提示原文，并附可授权核对的原件；启动异常会自动打开 STARTUP-ERROR.txt，请把报告里的文字反馈；完整日志同时保留在 data。

验证说明
已验证本地API、业务规则、构建和回归；交付前没有在Windows实机或金山桌面应用中验收。
请负责人先完成演示资料流程，再用真实样本逐项核对金额、数量、交期和版式。
'''
    if factory == 'huakang-b':
        common += '''
华康B使用顺序
1. 排期参照、货价表保存一次后会自动复用，仅在表格有更新时替换。有“预置参照说明.txt”的包首次启动即载入随包参照。参照均可选，无参照也能解析生成；没有历史编号依据时编号留空，不会擅自从首号开始。
2. 上传 EML、邮件ZIP，或从邮件中直接复制正文表格粘贴；同一封邮件通常选一种方式。填写来单日期和金山人员名称对应的业务跟单。
3. 解析后查看明细。缺资料、候选价格和未识别来源只作提醒；本次生成已识别且选中的明细，缺值留空。改客名或装箱数后旧价清空，可之后补充。
4. 点击“生成问单Excel”直接生成44列文件，合同列统一为TBA，无需核对勾选或填写原因。文件保持待核对状态；生成不表示已经核准价格。
5. 已生成记录可下载原Excel，也可“复制全部44列”粘贴到Excel，不含表头；重复下载或复制不重新占号。剪贴板被限制时，按页面提示选中只读内容手动复制。

这是问单工具，不包含PO入正式排期入口。编号仅在本包数据中延续，不与线上或其他电脑共用。
试用编号不能直接作为多人共同使用的正式编号。
'''
    else:
        common += '''
订单／排期使用顺序
1. 选择本厂客户、上传客户PO与对应原排期，填写来单日期后解析。
2. 预览中的缺资料、数量或字段差异只作提醒，可直接保存或生成排期，不要求勾选核对或填写原因。缺值留空；同单号不同资料另存，已有订单和走货记录保留。
3. “保存订单”写入本机台账；“生成排期”下载完整排期副本。这是两个独立操作。
4. 缺货期可先入台账，补齐并保存货期后才能发送到本机部门收件箱；可登记分批走货，走货撤回须保留原因。
5. 本机发送记录不是发给线上员工的通知，也不会更新正式仓库、库存或生产任务。

已随包提供英文／简体中文 OCR 运行文件。扫描件的识别结果仍须核对。
少数旧 .xls 文件的保格式转换调用本机 Microsoft Excel；普通 .xlsx 不需要该转换。
本包不代替正式生产系统；本地发送、签收、走货记录需负责人核对流程后再决定正式上线方式。
'''
    if factory == 'huakang-a' and not green_toys_only:
        common += '\nZURU使用原排期专用流程：上传PDF/Excel PO及1至10份原周排期，生成独立18列新单汇总和对应原格式复制页。已有订单单独列出提醒；原周排期、MA和库存不修改。复制时选择数据行（不含表头）并粘贴值。\n'
    return common


def package_reference_seed(package: Path, schedule: Path, price: Path):
    """Only explicitly supplied private inputs enter this delivery, never Git sources."""
    directory = package / 'reference-seed'
    directory.mkdir()
    records = []
    for kind, source in (('schedule', schedule), ('price', price)):
        if source.is_symlink() or source.suffix.lower() != '.xlsx' or not 0 < source.stat().st_size <= 20 * 1024**2:
            raise ValueError('Initial JP references must be regular XLSX files under 20MB.')
        content = source.read_bytes()
        (directory / (kind + '.xlsx')).write_bytes(content)
        records.append({'kind': kind, 'file': kind + '.xlsx', 'name': source.name,
            'sha256': sha256(content).hexdigest()})
    (directory / 'manifest.json').write_text(json.dumps({'format': 1, 'factory_id': 'huakang-b',
        'files': records}, ensure_ascii=False, indent=2), encoding='utf-8')
    environment = {**os.environ, 'PYTHONPATH': str(package / 'backend'), 'PYTHONDONTWRITEBYTECODE': '1'}
    validation = subprocess.run([sys.executable, '-B', '-m', 'app.reference_seed', str(directory)],
        env=environment, check=True, capture_output=True, text=True)
    return json.loads(validation.stdout)


def build(cache: Path, output: Path, selected, release_date: str | None = None,
        jp_schedule: Path | None = None, jp_price: Path | None = None, green_toys_only: bool = False, huaxing_customer: str | None = None,
        legacy_windows: bool = False, single_customer: str | None = None):
    if single_customer and ((selected not in [['huakang-a'], ['huaxing']] if single_customer == 'zuru' else selected != [SINGLE_CUSTOMERS.get(single_customer, ('', ''))[0]]) or green_toys_only or huaxing_customer):
        raise ValueError('专客包必须选择对应厂区及唯一客户')
    if legacy_windows and not (single_customer or huaxing_customer or selected == ['huakang-b'] or (green_toys_only and selected == ['huakang-a'])):
        raise ValueError('Windows 7兼容构建需选择已验证的专客模式。')
    if huaxing_customer and (selected != ['huaxing'] or huaxing_customer not in {'caixing','edu','dickie','seasons'}):
        raise ValueError('华兴专客包需指定华兴及一个支持客户')
    if green_toys_only and selected != ['huakang-a']:
        raise ValueError('Green Toys专用包必须只选择华康A。')
    seeded = jp_schedule is not None or jp_price is not None
    if seeded and (jp_schedule is None or jp_price is None or 'huakang-b' not in selected):
        raise ValueError('Supply both JP references and include huakang-b in the selected delivery.')
    release_day = date.fromisoformat(release_date) if release_date else datetime.now(ZoneInfo("Asia/Shanghai")).date()
    release = release_day.isoformat()
    stamp = release_day.strftime("%Y%m%d")
    output.mkdir(parents=True, exist_ok=True)
    source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    records = []
    with tempfile.TemporaryDirectory(prefix='factory-trial-delivery-', dir=cache) as temporary:
        staging = Path(temporary)
        shared_runtime = staging / 'runtime'
        dependencies = runtime(cache, shared_runtime, True) if legacy_windows else runtime(cache, shared_runtime)
        for factory in selected:
            zip_name, folder, name, customers = FACTORIES[factory]
            if green_toys_only:
                zip_name, folder, customers = '01_华康A_GreenToys_订单入排期', 'HuakangA_GreenToys_Trial', 'Green Toys'
            if legacy_windows and green_toys_only:
                zip_name, folder = '华康A_GreenToys_Win7_Win10_32及64位', 'GT_Trial'
            if legacy_windows and factory == 'huakang-b':
                zip_name, folder = '华康B_JP问单_Win7_Win10_32及64位', 'HuakangB_JP_Trial'
            if single_customer:
                customers = SINGLE_CUSTOMERS[single_customer][1]
                folder = f'{customers}_Trial'
                if single_customer == 'zuru':
                    folder = ('HuakangA' if factory == 'huakang-a' else 'Huaxing') + '_ZURU_Trial'
                zip_name = f'{name}_{customers}' + ('_Win7_Win10_32及64位' if legacy_windows else '')
            if huaxing_customer:
                customers = {'caixing':'彩星','edu':'EDU','dickie':'Dickie','seasons':'施信'}[huaxing_customer]
                zip_name, folder = f'05_华兴_{customers}_订单入排期', f'Huaxing_{huaxing_customer}_Trial'
                if legacy_windows:
                    zip_name = f'华兴_{customers}_Win7_Win10_32及64位'
            kind = 'jp' if factory == 'huakang-b' else 'orders'
            source = ROOT / 'tools' / ('huakang-b-jp-trial' if kind == 'jp' else 'customer-order-trial')
            package = staging / folder
            package.mkdir()
            subprocess.run([sys.executable, '-B', str(source / 'prepare_backend.py'), str(package / 'backend')], check=True)
            has_seed = kind == 'jp' and seeded
            if has_seed:
                stats = package_reference_seed(package, jp_schedule, jp_price)
                (package / '预置参照说明.txt').write_text(
                    '本包已带上交付时指定的华康B排期和货价原件副本。首次启动自动保存，后续自动复用。\n'
                    '日常直接导入邮件；只有原表更新时，才在“当前参照”选择新文件并点击“验证并更新”。\n'
                    '关闭页面或重启不会丢失；请保留整个data文件夹。\n'
                    '如迁移旧包data，已有参照和导出历史优先保留，不会被预置文件覆盖。\n'
                    '需要采用本包的新参照时，在页面选择reference-seed内对应XLSX更新一次即可。\n'
                    'schedule.xlsx为排期，price.xlsx为货价；原始文件名及校验见manifest.json。\n'
                    '本包包含指定的业务参照，请交给相应华康B试用人员。\n'
                    f'校验记录数：排期{stats["schedule"]["rows"]}，货价{stats["price"]["rows"]}。\n', encoding='utf-8-sig')
            # Validate references with the build host before adding Python 3.8
            # backports, which are installed only in the Windows runtime.
            if legacy_windows:
                from legacy_python import prepare
                prepare(package / 'backend')
            web = source / 'build' / ('web-single-customer' if single_customer else 'web-huaxing-recent' if huaxing_customer else 'web-green-toys' if green_toys_only else 'web-huadeng' if factory == 'huadeng' else 'web')
            if not (web / 'index.html').is_file():
                raise RuntimeError(f'Missing built frontend: {web}')
            frontend_manifest = json.loads((web / 'source-manifest.json').read_text(encoding='utf-8'))
            if single_customer or green_toys_only or huaxing_customer or factory == 'huadeng':
                expected_mode = 'single-customer' if single_customer else 'huaxing-recent' if huaxing_customer else 'green-toys' if green_toys_only else 'huadeng'
                expected_entry = 'src/singleCustomerMain.ts' if single_customer else 'src/huaxingTrialMain.ts' if huaxing_customer else 'src/greenToysMain.ts' if green_toys_only else 'src/huadengMain.ts'
                if (frontend_manifest.get('build_mode') != expected_mode or frontend_manifest.get('entry') != expected_entry
                        or not all(frontend_manifest.get(k) for k in ('sources', 'contracts', 'local_sources'))):
                    raise RuntimeError('Missing or incorrect standalone frontend manifest; rebuild the selected mode')
            for entry in frontend_manifest.get('sources', []) + frontend_manifest.get('contracts', []) + frontend_manifest.get('local_sources', []):
                if sha256((ROOT / entry['path']).read_bytes()).hexdigest() != entry['sha256']:
                    raise RuntimeError(f'Stale frontend source: {entry["path"]}; rebuild before packaging')
            copy_tree(web, package / 'web')
            copy_tree(shared_runtime, package / 'runtime')
            shutil.copyfile(TOOL / 'launch.py', package / 'launch.py')
            (package / 'START.cmd').write_bytes(START.encode('ascii'))
            instructions = readme(factory, release, green_toys_only)
            if legacy_windows:
                instructions = instructions.replace('Windows 10/11 64位电脑。', 'Windows 7 SP1、Windows 10，32位和64位电脑。')
                instructions = instructions.replace('页面会在默认浏览器打开', '页面会在随包浏览器打开')
                shutil.copyfile(TOOL / 'windowed_start.py', package / 'windowed_start.py')
                (package / 'OPEN.vbs').write_bytes((TOOL / 'start-windowed.vbs').read_text(encoding='ascii').replace('\n', '\r\n').encode('ascii'))
                instructions += '\n备用启动：双击 OPEN.vbs，通过随包 pythonw 打开程序，不使用控制台输出。关闭程序窗口后，本机服务正常退出，数据保留。重复点击会聚焦同一窗口。若电脑禁用脚本，使用 START.cmd。两个入口使用同一个 data，不要重复复制业务数据。\n'
                instructions += '\n本包使用32位运行环境，可在32位和64位Windows运行，无需选择版本。\nWindows 7需已安装SP1及微软通用C运行库更新（KB2999226）。如提示缺少api-ms-win-crt或VCRUNTIME DLL，请运行随包support/VC_redist.x86.exe安装微软官方运行库，再重新启动；即使64位电脑也用本包的x86安装文件。系统缺少SP1时需先由电脑维护人员更新。\n随包浏览器仅打开本机试用页面。程序启动失败时会自动打开STARTUP-ERROR.txt，报告汇总了完整启动日志，请复制内容反馈。\n'
                copy_tree(TOOL / 'desktop', package / 'desktop')
                extract(cache / 'electron-v22.3.27-win32-ia32.zip', package / 'browser')
                (package / 'support').mkdir()
                shutil.copyfile(cache / 'vc_redist.x86.exe', package / 'support' / 'VC_redist.x86.exe')
            if green_toys_only:
                instructions = instructions.replace(FACTORIES[factory][3], 'Green Toys')
                instructions += '\n本包直接复用GitHub订单中心导入/预览页面和外框样式，只开放Green Toys。\n货期可留空直接生成，后续在Excel手动填写。请勿混入其他客户的data目录。\n'
            if huaxing_customer:
                instructions = instructions.replace(FACTORIES[factory][3], customers)
                instructions += f'\n本包仅开放华兴{customers}，直接复用GitHub订单中心页面；请使用该客户自己的排期。\n'
                if huaxing_customer == 'seasons':
                    instructions += '施信预备单写入“预备单”区；正式PO有明确QF号和同货号时关联扣数，QF与正式单上下相邻。重复导入不重复扣数。无法唯一关联时提醒并保留，来源版本冲突另列ITEM待补资料、不计入三表合计。原价未提供时留空；排期内人工填写的价格保留。\n'
            if factory == 'huadeng' and not single_customer:
                instructions += '\n本包直接复用GitHub订单中心导入、预览、台账和排期页面，开放华登五客；资料提醒不要求填写放行原因。\nJakks原单Line#区分分批，完全相同历史批次不重复追加。取消通知保留原始数量证据，订单类型标为取消单。\n'
            if single_customer:
                instructions = instructions.replace(FACTORIES[factory][3], customers)
                instructions += f'\n本包只开放{name} {customers}，前端直接复用 GitHub 客户订单中心。新包请勿混入其他客户的 data。\n'
                if single_customer == 'zuru':
                    instructions = instructions.replace('“生成排期”下载完整排期副本', '“生成排期”下载独立新单汇总')
                    if 'ZURU使用原排期专用流程' not in instructions:
                        instructions += '\nZURU使用原排期专用流程：上传PDF/Excel PO及1至10份原周排期，生成独立18列新单汇总和对应原格式复制页。已有订单单独列出提醒；原周排期、MA和库存不修改。复制时选择数据行（不含表头）并粘贴值。\n'
                if single_customer == 'casdon':
                    instructions += '货号保留原单写法，AW/SS版本不拼接到货号；新单插入各表同货号的有效订单组，原历史不覆盖。旧文件里已有的错误尾码或重复记录不会自动清除，请保留原件核对。\n'
            if factory == 'huadeng':
                instructions += '生成排期时补齐ITEM主表的跟单、版本、国家、船务、QC、品牌、条码等缺失表头。已有同义表头保留；船务和QC数据仍需手动录入，补表头不代表自动导入。产品单价按美元/港币分别显示，开票价格独立留空。\n'
            if has_seed:
                instructions = instructions.replace('请负责人先完成演示资料流程，再用真实样本逐项核对金额、数量、交期和版式。',
                    '本包已预置参照，可直接导入真实邮件。演示操作请在另一个解压副本中进行，不要把演示数据迁入日常工作副本。')
            (package / '先看使用说明.txt').write_text(instructions, encoding='utf-8-sig')
            (package / 'trial.json').write_text(json.dumps({'kind': kind, 'factory_id': factory,
                'name': f'{name}问单本地试用' if kind == 'jp' else f'{name}订单排期本地试用',
                'release': release, 'source_commit': source_commit, 'reference_seed': has_seed,
                **({'runtime_profile': 'win7-sp1-win10-x86', 'architectures': ['x86', 'x64']} if legacy_windows else {}),
                **({'customer_codes': [single_customer]} if single_customer else {'customer_codes': [huaxing_customer]} if huaxing_customer else {'customer_codes': ['green-toys']} if green_toys_only else {}),
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
                    if huaxing_customer:
                        command += ['--huaxing-customer', huaxing_customer]
                    if single_customer:
                        command += ['--single-customer', single_customer]
                    if green_toys_only:
                        command += ['--green-toys-only']
                subprocess.run(command, check=True)
                if has_seed:
                    demo_instructions = package / '演示资料/演示操作说明.txt'
                    demo_instructions.write_text('本包已预置真实参照，日常录入无需上传下列演示参照。\n'
                        '以下演示仅在另一个解压副本中进行；不要把演示data复制回日常工作包。\n\n'
                        + demo_instructions.read_text(encoding='utf-8-sig'), encoding='utf-8-sig')
            (package / 'DEPENDENCIES.json').write_text(json.dumps(dependencies, indent=2), encoding='utf-8')
            for filename in (('runtime-sources-win7.json', 'requirements-win7.txt') if legacy_windows else ('runtime-sources.json', 'requirements-windows.txt')):
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
    if set(selected) == set(FACTORIES):
        (output / '06_华康C_当前状态说明.txt').write_text('华康C当前没有开放的普通客户订单／排期入口。\n'
            '本次没有生成会重新开放隐藏或历史客户映射的试用程序。\n华康C裁床/BOM/生产模块不在本次订单问单试用范围。\n', encoding='utf-8-sig')
    with (output / '00_交接登记.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['厂区', '试用包', '客户／功能', '对接人', '交付日期', '启动结果', '试用问题'])
        for factory in selected:
            filename, _, name, customers = FACTORIES[factory]
            if green_toys_only:
                filename, customers = '01_华康A_GreenToys_订单入排期', 'Green Toys'
            if legacy_windows and green_toys_only:
                filename = '华康A_GreenToys_Win7_Win10_32及64位'
            if legacy_windows and factory == 'huakang-b':
                filename = '华康B_JP问单_Win7_Win10_32及64位'
            if single_customer:
                customers = SINGLE_CUSTOMERS[single_customer][1]
                filename = f'{name}_{customers}' + ('_Win7_Win10_32及64位' if legacy_windows else '')
            if huaxing_customer:
                customers = {'caixing':'彩星','edu':'EDU','dickie':'Dickie','seasons':'施信'}[huaxing_customer]
                filename = f'05_华兴_{customers}_订单入排期'
                if legacy_windows:
                    filename = f'华兴_{customers}_Win7_Win10_32及64位'
            writer.writerow([name, f'{filename}_Windows试用_{stamp}.zip', customers, '', '', '', ''])
    overview = ('各厂区订单／排期与华康B问单｜Windows单机试用包\n\n'
        + '本文件夹包含：' + '、'.join(FACTORIES[key][2] for key in selected) + '。\n' +
        '每个ZIP都是独立包，请把对应厂区的ZIP交给负责人，完整解压后双击START.cmd。\n'
        '不需要总系统账号。仅适用于Windows 10/11 64位。\n'
        '功能范围：华康B只保留JP问单；订单包包含本地订单台账、发送收件、分批走货和排期生成。\n'
        '数据保存在各自解压目录的data中，互不共享，不写入线上系统。\n'
        '发票不在本次范围。各厂区数据和压缩包独立。\n'
        '00_交接登记.csv可填写负责人及反馈。各包内有详细使用说明。\n'
        'Windows实机和金山导入尚需对接人现场试用核对；本地API/业务回归与构建验证见交付验证说明。\n')
    if legacy_windows:
        overview = overview.replace('仅适用于Windows 10/11 64位。', '本兼容包适用于Windows 7 SP1与Windows 10的32位和64位；Win7需微软通用C运行库更新。')
    (output / '00_总说明_先看这里.txt').write_text(overview, encoding='utf-8-sig')
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--factory', action='append', choices=FACTORIES)
    parser.add_argument('--release-date', help='Release date YYYY-MM-DD; defaults to the Shanghai calendar date.')
    parser.add_argument('--huaxing-customer', choices=['caixing','edu','dickie','seasons'])
    parser.add_argument('--jp-schedule', type=Path, help='Explicit private initial JP schedule XLSX; shipped only in the B ZIP.')
    parser.add_argument('--jp-price', type=Path, help='Explicit private initial JP price XLSX; requires --jp-schedule.')
    parser.add_argument('--green-toys-only', action='store_true', help='Huakang A Green Toys only; reuse the GitHub order workspace frontend.')
    parser.add_argument('--single-customer', choices=SINGLE_CUSTOMERS)
    parser.add_argument('--legacy-windows', action='store_true', help='Win7 SP1/Win10 x86 runtime and bundled local browser; validated single-customer profiles.')
    args = parser.parse_args()
    build(args.cache.resolve(), args.output.resolve(), args.factory or list(FACTORIES), args.release_date,
        args.jp_schedule, args.jp_price, args.green_toys_only, args.huaxing_customer, args.legacy_windows, args.single_customer)
