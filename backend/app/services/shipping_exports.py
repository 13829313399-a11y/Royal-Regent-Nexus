"""Copy generated shipping workbooks into the shared D:\\导入文件 drop folders."""
from datetime import datetime
from pathlib import Path
import re

EXPORT_ROOT = Path(r'D:\导入文件')
FOLDERS = {
    'so_dk': 'SO 出货表',
    'so_zuru': 'SO 出货表',
    'truck_buzzbee': '车的排出货表',
    'truck_bulk': '车的排出货表',
    'truck_export': '车的排出货表',
    'supplement': '补料单',
    'customs': '通关一体化资料',
}
MONTHLY_SORTED_MODULES = {'so_dk', 'so_zuru', 'truck_buzzbee', 'truck_bulk', 'truck_export', 'supplement'}


def _safe_name(filename: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename).strip(' .')
    return name or 'shipping.xls'


def build_so_target(folder: Path, filename: str, now: datetime | None = None) -> Path:
    """Build <YYYY年MM月>/<filename> monthly archive path."""
    current = now or datetime.now()
    month_dir = folder / f'{current.year}年{current.month:02d}月'
    return month_dir / _safe_name(filename)


def save_import_file(module: str, filename: str, content: bytes, now: datetime | None = None) -> str:
    base_folder = EXPORT_ROOT / FOLDERS[module] if module in FOLDERS else EXPORT_ROOT
    try:
        if module in MONTHLY_SORTED_MODULES:
            path = build_so_target(base_folder, filename, now=now)
        else:
            path = base_folder / _safe_name(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)
    except OSError:
        return ''
