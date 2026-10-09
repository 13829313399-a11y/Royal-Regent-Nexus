"""Admin-only installation from an existing, lawfully obtained model directory."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path


def install(source, target, manifest):
    assets = []
    for model in json.loads(manifest.read_text(encoding="utf-8"))["models"].values():
        assets.append((Path(model["url"]).name, model["size"], model["sha256"]))
        if model.get("dictUrl"):
            assets.append((Path(model["dictUrl"]).name, model["dictSize"], model["dictSha256"]))
    # Validate every asset before touching the installed set.
    for name, size, digest in assets:
        file = source / name
        with file.open("rb") as stream:
            if file.stat().st_size != size or hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                raise ValueError(f"模型校验失败：{name}")
    target.mkdir(parents=True, exist_ok=True)
    for name, _, _ in assets:
        temporary = target / (name + ".installing")
        shutil.copyfile(source / name, temporary)
        os.replace(temporary, target / name)
    print(f"已校验并安装 {len(assets)} 个服务器模型文件。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, default=Path(__file__).resolve().parents[1] / "models/image-translation")
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[2] / "shinobu-web/server/dist/models.json")
    args = parser.parse_args()
    install(args.source_dir.resolve(), args.model_dir.resolve(), args.manifest.resolve())
