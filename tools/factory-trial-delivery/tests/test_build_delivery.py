"""Packaging boundary checks use tiny synthetic archives, never customer data."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
from zipfile import ZipFile, ZipInfo

import pytest

TOOL = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("trial_delivery_builder", TOOL / "build_delivery.py")
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


def archive(path, entries):
    with ZipFile(path, "w") as zipped:
        for name, content in entries:
            zipped.writestr(name, content)
    return path


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/drive", "ok\\escape", "a/../../escape",
    "file:stream", "CON.txt", "folder/NUL", "trailing. ", "a//b"])
def test_unsafe_windows_archive_names_rejected_before_writing(tmp_path, name):
    zipped = archive(tmp_path / "bad.zip", [("safe.txt", "safe"), (name, "bad")])
    target = tmp_path / "unpacked"
    with pytest.raises(ValueError, match="Unsafe"):
        delivery.extract(zipped, target)
    assert not target.exists()


def test_symlink_case_collision_and_existing_target_are_rejected(tmp_path):
    link = ZipInfo("link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError, match="Unsafe"):
        delivery.extract(archive(tmp_path / "link.zip", [(link, "outside")]), tmp_path / "links")
    with pytest.raises(ValueError, match="Unsafe"):
        delivery.extract(archive(tmp_path / "case.zip", [("File", "a"), ("file", "b")]), tmp_path / "case")
    target = tmp_path / "existing"
    target.mkdir()
    (target / "keep").write_text("original")
    with pytest.raises(ValueError, match="overwrites"):
        delivery.extract(archive(tmp_path / "overwrite.zip", [("keep", "overwrite")]), target)
    assert (target / "keep").read_text() == "original"


def wheel(cache, name, version="1.0", requires=(), tag="py3-none-any"):
    path = cache / "wheels-pinned" / f"{name}-{version}-{tag}.whl"
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nRequires-Python: >=3.12\n"
    metadata += "".join(f"Requires-Dist: {requirement}\n" for requirement in requires)
    return archive(path, [(f"{name}-{version}.dist-info/METADATA", metadata), (f"{name}.py", "")])


def pins(tmp_path, monkeypatch, text):
    tool = tmp_path / "tool"
    tool.mkdir()
    (tool / "requirements-windows.txt").write_text(text)
    monkeypatch.setattr(delivery, "TOOL", tool)


def test_dependency_closure_evaluates_windows_markers_and_exact_set(tmp_path, monkeypatch):
    pins(tmp_path, monkeypatch, "demo==1.0\n")
    wheel(tmp_path, "demo", requires=['colorama>=0.4; sys_platform == "win32"'])
    with pytest.raises(ValueError, match="Unsatisfied Windows dependency"):
        delivery.dependency_inventory(tmp_path)
    (delivery.TOOL / "requirements-windows.txt").write_text("demo==1.0\ncolorama==0.4.6\n")
    with pytest.raises(ValueError, match="Missing pinned"):
        delivery.dependency_inventory(tmp_path)
    wheel(tmp_path, "colorama", "0.4.6")
    records = delivery.dependency_inventory(tmp_path)
    assert {record["name"] for record in records} == {"demo", "colorama"}
    wheel(tmp_path, "unexpected")
    with pytest.raises(ValueError, match="Unexpected"):
        delivery.dependency_inventory(tmp_path)


@pytest.mark.parametrize("tag", ["cp311-cp311-win_amd64", "cp312-cp312-win32", "cp312-cp312-macosx_11_0_arm64"])
def test_non_target_native_wheels_rejected(tmp_path, monkeypatch, tag):
    pins(tmp_path, monkeypatch, "demo==1.0\n")
    wheel(tmp_path, "demo", tag=tag)
    with pytest.raises(ValueError, match="not compatible"):
        delivery.dependency_inventory(tmp_path)


@pytest.mark.parametrize("relative", ["data/history.sqlite3", ".env.production", "backend/__pycache__/module.pyc",
    "backend/.git/config", "secret.pem", "history.db-wal"])
def test_trial_state_and_credentials_never_enter_package(tmp_path, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic forbidden data")
    with pytest.raises(ValueError, match="Forbidden delivery artifact"):
        delivery.package_hashes(tmp_path)


def test_backend_manifest_mismatch_stops_delivery(tmp_path, monkeypatch):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/module.py").write_text("changed")
    (tmp_path / "backend/source-manifest.json").write_text(json.dumps({"files": [
        {"target": "module.py", "sha256": sha256(b"original").hexdigest()}]}))
    with pytest.raises(ValueError, match="source manifest mismatch"):
        delivery.build_provenance(tmp_path, tmp_path, "base")


def test_package_rejects_paths_requiring_windows_long_path_support(tmp_path):
    path = tmp_path / ("a" * 90) / ("b" * 90) / ("c" * 90 + ".txt")
    path.parent.mkdir(parents=True)
    path.write_text("synthetic")
    with pytest.raises(ValueError, match="MAX_PATH"):
        delivery.package_hashes(tmp_path)


def test_small_delivery_has_no_pyc_and_honest_source_hashes(tmp_path, monkeypatch):
    root = tmp_path / "中文 空格 源码"
    tool = root / "tools/factory-trial-delivery"
    source = root / "tools/huakang-b-jp-trial"
    tool.mkdir(parents=True)
    (source / "build/web").mkdir(parents=True)
    (source / "build/web/index.html").write_text("<html>synthetic</html>")
    (tool / "launch.py").write_text("# synthetic launcher")
    (tool / "requirements-windows.txt").write_text("demo==1.0\n")
    (tool / "runtime-sources.json").write_text("{}")
    (source / "prepare_backend.py").write_text('''
import sys, json
from pathlib import Path
from hashlib import sha256
p=Path(sys.argv[1]);p.mkdir()
content=b"VALUE = 1\\n";(p/'demo.py').write_bytes(content)
(p/'source-manifest.json').write_text(json.dumps({'files':[{'target':'demo.py','sha256':sha256(content).hexdigest()}]}))
''')
    (source / "create_demo.py").write_text('''
import sys
from pathlib import Path
p=Path(sys.argv[1]);p.mkdir()
sys.path.insert(0,str(p.parent/'backend'))
import demo
(p/'synthetic.txt').write_text('synthetic demo only')
''')
    monkeypatch.setattr(delivery, "ROOT", root)
    monkeypatch.setattr(delivery, "TOOL", tool)
    def fake_runtime(cache, destination):
        destination.mkdir()
        (destination / "python.exe").write_bytes(b"synthetic runtime")
        return [{"name": "demo", "version": "1.0"}]
    monkeypatch.setattr(delivery, "runtime", fake_runtime)
    monkeypatch.setattr(delivery.subprocess, "check_output", lambda args, **kwargs:
        "base-commit\n" if args[1] == "rev-parse" else "?? tools/standalone\n")
    cache = tmp_path / "cache"
    cache.mkdir()
    output = tmp_path / "output"
    result = delivery.build(cache, output, ["huakang-b"])
    zipped_path = output / result[0]["file"]
    with ZipFile(zipped_path) as zipped:
        names = zipped.namelist()
        assert not any("__pycache__" in name or name.endswith(".pyc") or "/data/" in name for name in names)
        prefix = "HuakangB_JP_Trial/"
        provenance = json.loads(zipped.read(prefix + "BUILD-SOURCES.json"))
        assert provenance["working_tree_has_changes"] and provenance["base_commit"] == "base-commit"
        source_entry = next(item for item in provenance["build_inputs"] if item["path"].endswith("/create_demo.py"))
        assert source_entry["sha256"] == sha256((source / "create_demo.py").read_bytes()).hexdigest()
        manifest = json.loads(zipped.read(prefix + "PACKAGE-MANIFEST.json"))
        for item in manifest["files"]:
            content = zipped.read(prefix + item["path"])
            assert sha256(content).hexdigest() == item["sha256"] and len(content) == item["bytes"]
        assert "uncommitted" in manifest["source_commit_role"]
        assert zipped.read(prefix + "START.cmd").endswith(b"if errorlevel 1 pause\r\n")
    assert sha256(zipped_path.read_bytes()).hexdigest() == result[0]["sha256"]
    assert not list(output.glob("*.part"))


def test_available_real_cache_has_complete_pinned_windows_dependencies():
    cache = delivery.ROOT.parent / "trial-runtime-cache"
    if not (cache / "wheels-pinned").is_dir():
        pytest.skip("Release cache is not present on this development computer")
    records = delivery.dependency_inventory(cache)
    assert len(records) == 35
    assert any(record["name"].lower() == "colorama" for record in records)
    sources = delivery.verify_native_sources(cache)
    assert len(sources["native_downloads"]) == 3 and len(sources["ocr_languages"]) == 2
