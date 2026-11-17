"""Copy generated shipping workbooks into the shared D:\\导入文件 drop folders."""
from pathlib import Path
import re

EXPORT_ROOT = Path(r'D:\导入文件')
FOLDERS = {
    'so_dk': 'SO 出货表',
    'so_zuru': 'SO 出货表',
    'truck_buzzbee': '车的排出货表',
    'truck_bulk': '车的排出货表',
    'supplement': '补料',
    'customs': '通关一体化资料',
}


def _safe_name(filename: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename).strip(' .')
    return name or 'shipping.xls'


def save_import_file(module: str, filename: str, content: bytes) -> str:
    folder = EXPORT_ROOT / FOLDERS[module] if module in FOLDERS else EXPORT_ROOT
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / _safe_name(filename)
        path.write_bytes(content)
        return str(path)
    except OSError:
        return ''
