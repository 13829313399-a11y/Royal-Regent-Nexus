"""Private manifests provide opt-in evidence without publishing business fixtures."""
import json

import pytest

from customer_order_360_private_samples import (
    MANIFEST_ENV, load_private_manifest, private_po_samples, require_private_manifest,
)


def test_missing_private_manifest_skips_evidence_without_loading_any_default_path(monkeypatch):
    monkeypatch.delenv(MANIFEST_ENV, raising=False)
    assert load_private_manifest() is None
    case, = private_po_samples()
    assert case.values == (None,)
    assert any(mark.name == "skip" for mark in case.marks)
    with pytest.raises(pytest.skip.Exception):
        require_private_manifest()


def test_external_manifest_supplies_filenames_and_expected_fields_without_leaking_test_ids(tmp_path, monkeypatch):
    manifest = {
        "po_directory": "private-pos", "schedule": "private-schedule.xlsx",
        "received_date": "2030-01-01",
        "samples": [{"file": "private-example.pdf", "expected": {
            "reference_no": "RL-123456-1", "product_no": "12345670001", "shipping_item": "1234567",
        }}],
        "validation_checks": [],
    }
    source = tmp_path / "private-manifest.json"
    source.write_text(json.dumps(manifest), encoding="utf-8")
    before = source.read_bytes()
    monkeypatch.setenv(MANIFEST_ENV, str(source))
    loaded = require_private_manifest()
    assert loaded["po_directory"] == tmp_path / "private-pos"
    assert loaded["schedule"] == tmp_path / "private-schedule.xlsx"
    case, = private_po_samples()
    assert case.id == "private-sample-001"
    sample, = case.values
    assert sample["source"] == tmp_path / "private-pos/private-example.pdf"
    assert sample["expected"] == manifest["samples"][0]["expected"]
    assert sample["manifest"] == loaded
    assert source.read_bytes() == before


@pytest.mark.parametrize("samples", [[], [None], [{"file": "sample.pdf"}]])
def test_configured_but_incomplete_private_manifest_fails_instead_of_silently_skipping(tmp_path, monkeypatch, samples):
    source = tmp_path / "private-manifest.json"
    source.write_text(json.dumps({"po_directory": ".", "schedule": "sample.xlsx", "samples": samples}), encoding="utf-8")
    monkeypatch.setenv(MANIFEST_ENV, str(source))
    with pytest.raises(ValueError, match="private 360|Private 360"):
        private_po_samples()
