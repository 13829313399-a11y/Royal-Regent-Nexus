"""Verify every pinned upstream file, including explicitly recorded Nexus adaptations."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[1] / "services" / "indonesia-shipping"
upstream = json.loads((root / "UPSTREAM.json").read_text(encoding="utf-8"))
patches = json.loads((root / "NEXUS_PATCHES.json").read_text(encoding="utf-8"))["adapted_files"]
errors = []
for relative, original in upstream["files"].items():
    path = root / relative
    expected = patches.get(relative, original)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        errors.append(relative)
if set(patches) - set(upstream["files"]):
    errors.append("NEXUS_PATCHES contains files absent from pinned upstream")
if errors:
    raise SystemExit("Source integrity mismatch: " + ", ".join(errors))
print(f"Verified {len(upstream['files'])} upstream files: {len(patches)} documented adaptations, {len(upstream['files']) - len(patches)} byte-identical originals")
