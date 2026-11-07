import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def test_private_template_preparation_does_not_overwrite_or_copy_into_git(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("prepare_invoice_templates", repo / "scripts/prepare-mainland-invoice-templates.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "source"
    originals = {}
    for factory, templates in module.TEMPLATES.items():
        for key, (folder, name) in templates.items():
            file = source / folder / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes((factory + key).encode())
            originals[file] = file.read_bytes()
    destination = tmp_path / "private-v1"
    module.prepare(source, destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    assert len(manifest) == 16
    assert destination.stat().st_mode & 0o777 == 0o700
    for entry in manifest:
        target = destination / entry["factory_id"] / entry["file_name"]
        assert hashlib.sha256(target.read_bytes()).hexdigest() == entry["sha256"]
        assert target.stat().st_mode & 0o777 == 0o600
    assert all(file.read_bytes() == value for file, value in originals.items())
    with pytest.raises(ValueError, match="目标已存在"):
        module.prepare(source, destination)
    with pytest.raises(ValueError, match="代码仓库外"):
        module.prepare(source, repo / "private-test-not-created")
    alias = tmp_path / "repo-alias"
    alias.symlink_to(repo, target_is_directory=True)
    with pytest.raises(ValueError, match="代码仓库外"):
        module.prepare(source, alias / "private-test-not-created")
