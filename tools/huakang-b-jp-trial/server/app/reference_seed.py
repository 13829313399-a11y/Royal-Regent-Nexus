"""Explicit private delivery references; fill missing kinds without replacing user data."""
from hashlib import sha256
import json
from pathlib import Path

from app.services.huakang_b_jp import intake
from app.services.transaction_lock import lock_transaction

KINDS = frozenset({"schedule", "price"})


def read_seed(directory):
    directory = Path(directory).resolve()
    manifest = directory / "manifest.json"
    if manifest.is_symlink() or manifest.stat().st_size > 16_384:
        raise ValueError("预置参照清单无效，请重新完整解压试用包。")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("format") != 1 or value.get("factory_id") != intake.FACTORY:
        raise ValueError("预置参照不是华康B试用包格式。")
    files = value.get("files")
    if not isinstance(files, list) or len(files) != 2 or any(not isinstance(row, dict) for row in files):
        raise ValueError("预置参照必须包含排期和货价两份文件。")
    if {row.get("kind") for row in files} != KINDS:
        raise ValueError("预置参照类型不正确。")
    result = []
    for row in files:
        kind = row["kind"]
        if row.get("file") != kind + ".xlsx":
            raise ValueError("预置参照路径无效。")
        path = directory / row["file"]
        name = row.get("name")
        if not isinstance(name, str) or not name.lower().endswith(".xlsx") or any(c in name for c in ("/", "\\", "\x00")):
            raise ValueError("预置参照名称无效。")
        if path.is_symlink() or not 0 < path.stat().st_size <= intake.MAX_FILE:
            raise ValueError("预置参照文件大小或路径无效。")
        content = path.read_bytes()
        if sha256(content).hexdigest() != row.get("sha256"):
            raise ValueError("预置参照文件校验失败，请重新完整解压试用包。")
        validation = intake._jp_validate_reference(kind, content)
        if validation["rows"] <= 0:
            raise ValueError("预置参照没有可识别的数据。")
        result.append((kind, name, content, validation))
    return result


def initialize_references(database, directory):
    with database.session() as session:
        if KINDS.issubset(intake.reference_state(session)):
            return  # Existing user versions are authoritative, even in a newer package.
    # Validate the entire pair before writing either kind.
    files = read_seed(directory)
    with database.session.begin() as session:
        lock_transaction(session, "jp-intake", intake.FACTORY)
        current = intake.reference_state(session)
        for kind, name, content, _ in files:
            if kind not in current:
                intake.save_reference(session, kind, name, content, 0, "试用包预置")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps({kind: stats for kind, _, _, stats in read_seed(args.directory)}, ensure_ascii=False))
