"""Build a separate V2-aware rollback artifact, without data or local configuration.

Usage: python backend/tools/build_iam_v2_compat.py --output NEW_ABSOLUTE_DIRECTORY
The source remains V2-aware; only new identity writes and UI are disabled.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def build(output):
    output = output.resolve()
    if output.exists() or output.is_relative_to(ROOT):
        raise ValueError("输出必须是仓库外尚不存在的目录，避免覆盖文件或混入运行数据")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("需要已安装的 Node.js；本工具不安装依赖")
    output.mkdir(parents=True)
    release = output / "release"
    (release / "backend").mkdir(parents=True)
    env = dict(os.environ, VITE_IAM_IDENTITY_UI_ENABLED="false")
    subprocess.run([node, str(ROOT / "node_modules/vite/bin/vite.js"), "build", "--outDir", str(release / "dist")],
                   cwd=ROOT, env=env, check=True)
    shutil.copytree(ROOT / "backend/app", release / "backend/app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".env*"))
    shutil.copytree(ROOT / "shared", release / "shared")
    shutil.copy2(ROOT / "backend/requirements.txt", release / "backend/requirements.txt")
    (release / "backend/iam_compat_entrypoint.py").write_text(
        '"""V2-compatible fallback: preserve canonical reads, disable new identity writes."""\n'
        'import os\nos.environ["IAM_IDENTITY_WRITES_ENABLED"] = "false"\n'
        'os.environ["IAM_IDENTITY_SCHEDULING_ENABLED"] = "false"\nfrom app.main import app\n', encoding="utf-8")
    files = {p.relative_to(release).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(release.rglob("*")) if p.is_file()}
    manifest = {"kind": "iam-v2-compatible-fallback", "required_migration": "20260926_0125",
        "identity_writes": False, "identity_scheduling": False, "identity_ui": False, "files": files,
        "database": "external_existing_migrated_database_required", "authz_mode": "preserve_existing_runtime_configuration"}
    (release / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (release / "README.txt").write_text(
        "IAM V2 兼容回退包。使用已迁移的原数据库，不做降级、不还原旧库、不切换 AUTHZ_MODE。\n"
        "设置 DATABASE_URL 和原运行配置；使用相同依赖环境启动：\n"
        "python -m uvicorn iam_compat_entrypoint:app --app-dir backend --host 127.0.0.1 --port 8000\n"
        "部署 dist 为前端。新任职办理界面关闭，后端保留 V2 时间线、epoch、来源和撤会话判定。\n"
        "该包不包含配置、业务数据、凭证或依赖环境。上线仍需单独授权。\n", encoding="utf-8")
    archive = output / "iam-v2-compatible-fallback.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(release.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(release))
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "artifact.sha256").write_text(checksum + "  " + archive.name + "\n", encoding="utf-8")
    return {"release": str(release), "archive": str(archive), "sha256": checksum, "files": len(files)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=False))
