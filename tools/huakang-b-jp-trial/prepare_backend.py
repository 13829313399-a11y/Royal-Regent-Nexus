"""Build an allowlisted JP backend without production data or credentials."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

API_SOURCE_SHA256 = "9cda4362dafd0b8cefdb07ae0272691957991351571b75d7b6fda2feceda9e8b"


def prepare(destination, repository=None):
    package = Path(__file__).resolve().parent
    repository = Path(repository).resolve() if repository else package.parents[1]
    destination = Path(destination).resolve()
    if destination == repository or destination == repository / "backend":
        raise ValueError("The trial staging directory must not replace the source repository.")
    source_api = repository / "backend/app/api/huakang_b_jp.py"
    if sha256(source_api.read_bytes()).hexdigest() != API_SOURCE_SHA256:
        raise RuntimeError("The JP host API changed; review the independent adapter before packaging.")
    sources = sorted((repository / "backend/app/services/huakang_b_jp").glob("*.py"))
    sources += [repository / "backend/app/models/huakang_b_jp.py",
        repository / "backend/app/schemas/huakang_b_jp.py",
        repository / "backend/app/services/transaction_lock.py"]
    records = []
    for source in sources:
        relative = source.relative_to(repository / "backend")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        records.append({"source": source.relative_to(repository).as_posix(), "target": relative.as_posix(),
            "sha256": sha256(source.read_bytes()).hexdigest()})
    adapters = []
    for source in sorted((package / "server").rglob("*.py")):
        relative = source.relative_to(package / "server")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        adapters.append({"source": source.relative_to(repository).as_posix(), "target": relative.as_posix(),
            "sha256": sha256(source.read_bytes()).hexdigest()})
    for directory in (destination / "app", destination / "app/api", destination / "app/services",
            destination / "app/models", destination / "app/schemas"):
        (directory / "__init__.py").touch()
    commit = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    manifest = {"source_commit": commit, "unchanged_business_sources": records, "standalone_adapters": adapters,
        "reviewed_host_api_source": {"source": source_api.relative_to(repository).as_posix(), "sha256": API_SOURCE_SHA256},
        "runtime": "Local SQLite and loopback HTTP; no production accounts, data or network database."}
    (destination / "source-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--repository", type=Path)
    arguments = parser.parse_args()
    report = prepare(arguments.destination, arguments.repository)
    print(json.dumps({"source_commit": report["source_commit"], "business_files": len(report["unchanged_business_sources"]),
        "adapter_files": len(report["standalone_adapters"]), "destination": str(arguments.destination)}, ensure_ascii=False))
