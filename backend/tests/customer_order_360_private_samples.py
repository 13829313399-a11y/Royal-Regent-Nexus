"""Opt-in private evidence; neither filenames nor expected business data live in Git.

Set HUAKANG_A_360_SAMPLE_MANIFEST to an external JSON file with:
  po_directory, schedule, received_date, samples, validation_checks.
Each samples entry has file and expected. Expected fields are the parser/preview
fields asserted by the consuming tests, including outer_carton_sticker_sources
as a list of page/raw_text objects. validation_checks contains sheet, include,
exclude and preserve_values. Paths may be absolute or relative to the manifest;
sample files are relative to po_directory. Keep this manifest outside Git.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


MANIFEST_ENV = "HUAKANG_A_360_SAMPLE_MANIFEST"


def load_private_manifest():
    configured = os.environ.get(MANIFEST_ENV)
    if not configured:
        return None
    source = Path(configured).expanduser().resolve()
    manifest = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("samples"), list) or not manifest["samples"]:
        raise ValueError("The private 360 manifest must contain a nonempty samples list")
    for field in ("po_directory", "schedule"):
        path = Path(manifest[field]).expanduser()
        manifest[field] = path if path.is_absolute() else source.parent / path
    for index, sample in enumerate(manifest["samples"], 1):
        if not isinstance(sample, dict) or not isinstance(sample.get("expected"), dict) or not sample.get("file"):
            raise ValueError(f"Private 360 sample {index} must define file and expected")
    return manifest


def private_po_samples():
    manifest = load_private_manifest()
    if manifest is None:
        return [pytest.param(None, id="private-manifest-not-configured",
                             marks=pytest.mark.skip(reason=f"Set {MANIFEST_ENV} to external read-only evidence"))]
    return [pytest.param({"source": manifest["po_directory"] / sample["file"],
                          "expected": sample["expected"], "manifest": manifest},
                         id=f"private-sample-{index:03d}")
            for index, sample in enumerate(manifest["samples"], 1)]


def require_private_manifest():
    manifest = load_private_manifest()
    if manifest is None:
        pytest.skip(f"Set {MANIFEST_ENV} to external read-only evidence")
    return manifest
