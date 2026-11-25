"""Build an offline Docker context for the reviewed QC-only overlay; never start services."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile


HERE = Path(__file__).resolve().parent


def git_blob(commit, path):
    return subprocess.check_output(["git", "-C", str(HERE), "show", f"{commit}:{path}"])


def checksums(values):
    return "".join(f"{values[p]}  {p}\n" for p in sorted(values)).encode()


def build_context():
    release = json.loads((HERE / "manifest.json").read_text())
    contents = {"Dockerfile": (HERE / "Dockerfile").read_bytes()}
    before, after = dict(release["unchanged"]), dict(release["unchanged"])
    for path, hashes in release["files"].items():
        data = git_blob(release["source"], path)
        if path == "backend/app/core/config.py":
            # Keep the rest of the installed shared API configuration byte-for-byte.
            base = git_blob(release["referenceBase"], path)
            anchor = b'    qc_mobile_public_origin: str = ""\n'
            fields = anchor + b"    qc_mobile_require_https: bool = False\n"
            if base.count(anchor) != 1 or fields not in data:
                raise ValueError("unexpected QC configuration layout")
            data = base.replace(anchor, fields)
        if hashlib.sha256(data).hexdigest() != hashes["candidate"]:
            raise ValueError(f"candidate differs from rehearsed inputs: {path}")
        contents["files/" + path] = data
        before[path], after[path] = hashes["expectedCurrent"], hashes["candidate"]
    contents.update({"before.sha256": checksums(before), "after.sha256": checksums(after)})

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", filename="", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name, data in sorted(contents.items()):
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
    return buf.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new .tar.gz file (will not overwrite)")
    output = parser.parse_args().output
    payload = build_context()
    with output.open("xb") as stream:
        stream.write(payload)
    print(f"{hashlib.sha256(payload).hexdigest()}  {output}")
