from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import BadZipFile, ZipFile


MODELS = {
    "zh_en": {
        "url": "https://argos-net.com/v1/translate-zh_en-1_9.argosmodel",
        "size": 74_481_402,
        "from_code": "zh",
        "to_code": "en",
    },
    "en_zh": {
        "url": "https://argos-net.com/v1/translate-en_zh-1_9.argosmodel",
        "size": 70_743_021,
        "from_code": "en",
        "to_code": "zh",
    },
}


def _download(url: str, destination: Path, expected_size: int) -> None:
    part_count = 8
    parts_dir = destination.with_suffix(destination.suffix + ".parts")
    parts_dir.mkdir(parents=True, exist_ok=True)
    chunk_size = (expected_size + part_count - 1) // part_count

    def download_part(index: int) -> Path:
        start = index * chunk_size
        end = min(expected_size - 1, start + chunk_size - 1)
        part_path = parts_dir / f"part-{index:02d}"
        expected_part_size = end - start + 1
        if part_path.is_file() and part_path.stat().st_size == expected_part_size:
            return part_path

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Royal-Regent-Nexus/1.0",
                "Range": f"bytes={start}-{end}",
            },
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            if getattr(response, "status", 200) != 206:
                raise RuntimeError("模型服务器不支持分段下载。")
            with part_path.open("wb") as target:
                shutil.copyfileobj(response, target, length=1024 * 1024)
        if part_path.stat().st_size != expected_part_size:
            raise RuntimeError(f"模型分段下载大小不正确：{part_path.name}")
        return part_path

    with ThreadPoolExecutor(max_workers=part_count) as executor:
        part_paths = list(executor.map(download_part, range(part_count)))

    partial = destination.with_suffix(destination.suffix + ".part")
    with partial.open("wb") as target:
        for part_path in part_paths:
            with part_path.open("rb") as source:
                shutil.copyfileobj(source, target, length=1024 * 1024)
    if partial.stat().st_size != expected_size:
        raise RuntimeError(f"模型合并后大小不正确：{destination.name}")
    partial.replace(destination)
    shutil.rmtree(parts_dir)


def _safe_extract(archive_path: Path, target_dir: Path, metadata: dict[str, object]) -> None:
    with ZipFile(archive_path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"模型压缩包校验失败：{bad_member}")
        members = archive.infolist()
        roots = {Path(member.filename).parts[0] for member in members if member.filename}
        if len(roots) != 1:
            raise RuntimeError("模型压缩包目录结构无效。")

        with tempfile.TemporaryDirectory(dir=target_dir.parent) as temp_name:
            temp_dir = Path(temp_name)
            for member in members:
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise RuntimeError("模型压缩包包含不安全路径。")
                archive.extract(member, temp_dir)

            package_root = temp_dir / next(iter(roots))
            package_metadata = json.loads((package_root / "metadata.json").read_text(encoding="utf-8"))
            if (
                package_metadata.get("from_code") != metadata["from_code"]
                or package_metadata.get("to_code") != metadata["to_code"]
            ):
                raise RuntimeError("模型语言方向与安装目标不一致。")
            if not (package_root / "model").is_dir() or not (package_root / "sentencepiece.model").is_file():
                raise RuntimeError("模型压缩包缺少推理文件。")

            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(package_root, target_dir)


def install_models(model_dir: Path, download_dir: Path) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)
    for name, metadata in MODELS.items():
        target = model_dir / name
        if (
            (target / "metadata.json").is_file()
            and (target / "model").is_dir()
            and (target / "sentencepiece.model").is_file()
        ):
            print(f"{name}: already installed")
            continue
        archive = download_dir / f"{name}.argosmodel"
        if not archive.is_file() or archive.stat().st_size != metadata["size"]:
            _download(str(metadata["url"]), archive, int(metadata["size"]))
        try:
            _safe_extract(archive, target, metadata)
        except BadZipFile as exc:
            raise RuntimeError(f"模型压缩包损坏：{archive.name}") from exc
        print(f"{name}: installed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install offline Chinese/English translation models.")
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--download-dir", type=Path)
    args = parser.parse_args()
    download_dir = args.download_dir or args.model_dir / ".downloads"
    install_models(args.model_dir.resolve(), download_dir.resolve())


if __name__ == "__main__":
    main()
