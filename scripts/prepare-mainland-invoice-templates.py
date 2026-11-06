"""Copy only approved A/B/D templates to a NEW private directory, never public."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.api.mainland_invoice import TEMPLATES


def prepare(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if destination == ROOT or ROOT in destination.parents:
        raise ValueError("目标必须在代码仓库外，不得放入公开或同步源码目录")
    if destination.exists():
        raise ValueError("目标已存在，请使用新的版本目录；本脚本不会覆盖旧模板")
    planned = []
    for factory, templates in TEMPLATES.items():
        for key, (folder, name) in templates.items():
            path = source / folder / name
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"缺少有效模板：{folder}/{name}")
            planned.append((factory, key, name, path))
    destination.mkdir(parents=True, mode=0o700)
    manifest = []
    for factory, key, name, path in planned:
        target = destination / factory / name
        target.parent.mkdir(exist_ok=True, mode=0o700)
        shutil.copyfile(path, target)
        target.chmod(0o600)
        manifest.append({
            "factory_id": factory, "template_id": key,
            "file_name": name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        })
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "manifest.json").chmod(0o600)
    print(f"已准备 {len(manifest)} 个模板；目标为私有目录，不包含兴信或备份模板。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-public", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source_public, args.destination)
