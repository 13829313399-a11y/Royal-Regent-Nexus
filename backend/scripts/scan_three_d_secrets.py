"""Bounded, offline secret checks; JSON output never contains source-controlled text.

--source-zip reads only .git/config, config.json, server.js and .env members
in memory without extracting or executing them. Business data/images/databases
are outside this fixed legacy-credential coverage, regardless of their size.
--tracked scans the Git index; --staged scans added/modified index entries.
--paths alone scans explicit worktree files; with a Git mode it filters pathspecs.
Exit codes: 0 clean, 1 findings, 2 incomplete/input failure (fail closed).
This is a targeted baseline check, not a comprehensive secret-detection engine.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable
import zipfile

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_FILES = 20000
RULES = ("github_token", "url_credentials", "private_key", "device_access_code", "basic_auth")
ZIP_ALLOWLIST = (".git/config", "config.json", "server.js", ".env")
SAFE_VALUES = {"", "changeme", "change_me", "replace-me", "replace_me", "replace-locally", "redacted", "<redacted>", "<secret>", "<password>", "<access-code>", "your_access_code", "your_password", "test-access-code", "dummy-access-code"}
PAT = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,255}|github_pat_[A-Za-z0-9_]{20,255})\b")
URL_AUTH = re.compile(r"[a-z][a-z0-9+.-]*://([^\s/@<>\"']+)@", re.I)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
VPN_KEY = re.compile(r"\bPrivateKey\s*=\s*([A-Za-z0-9+/]{43}=)", re.I)
ACCESS = re.compile(r"[\"']?(?:access[_ -]?code|lan[_ -]?access[_ -]?code|printer[_ -]?access[_ -]?code)[\"']?\s*[:=]\s*(?:[\"']([^\"'\r\n]*)[\"']|([0-9]{4,32})\b)", re.I)
ENV_ACCESS = re.compile(r"^\s*(?:[a-z0-9]+_)*(?:access_?code)\s*=\s*([^\s\"'#;]+)\s*(?:[#;].*)?$", re.I | re.M)
BASIC_FIELD = re.compile(r"[\"']?(?:basic[_ -]?auth[_ -]?(?:password|pass|token)|basic[_ -]?(?:password|pass))[\"']?\s*[:=]\s*[\"']([^\"'\r\n]+)[\"']", re.I)
BASIC_HEADER = re.compile(r"\bBasic\s+([A-Za-z0-9+/]{8,}={0,2})(?![A-Za-z0-9+/])", re.I)


def safe_placeholder(value: str) -> bool:
    value = value.strip()
    return value.lower() in SAFE_VALUES or bool(re.fullmatch(r"\$\{[A-Z_][A-Z0-9_]*\}", value))


def scan_text(text: str) -> dict[str, int]:
    counts = dict.fromkeys(RULES, 0)
    counts["github_token"] = len(PAT.findall(text))
    counts["private_key"] = len(PRIVATE_KEY.findall(text)) + len(VPN_KEY.findall(text))
    for match in URL_AUTH.finditer(text):
        parts = match.group(1).split(":", 1)
        if not safe_placeholder(parts[-1]):
            counts["url_credentials"] += 1
    for match in ACCESS.finditer(text):
        if not safe_placeholder(match.group(1) or match.group(2) or ""):
            counts["device_access_code"] += 1
    for match in ENV_ACCESS.finditer(text):
        value = match.group(1)
        if not safe_placeholder(value) and not re.fullmatch(r"[0-9]{4,32}", value):
            counts["device_access_code"] += 1
    counts["basic_auth"] += sum(not safe_placeholder(m.group(1)) for m in BASIC_FIELD.finditer(text))
    counts["basic_auth"] += len(BASIC_HEADER.findall(text))
    # Legacy JSON uses auth/basicAuth blocks with ordinary password keys.
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        data = None

    def walk(value: object, in_auth: bool = False) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = re.sub(r"[^a-z]", "", key.lower())
                if in_auth and normalized in {"password", "pass", "token"} and isinstance(item, str) and not safe_placeholder(item):
                    counts["basic_auth"] += 1
                walk(item, in_auth or normalized in {"auth", "basicauth", "basicauthentication"})
        elif isinstance(value, list):
            for item in value:
                walk(item, in_auth)

    try:
        walk(data)
    except RecursionError:
        raise ValueError("input_limit") from None
    return counts


def git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("git_input_error")
    return result.stdout


def git_blobs(staged: bool, paths: list[str]) -> Iterable[bytes]:
    command = ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"] if staged else ["ls-files", "-z"]
    names = git(*command, "--", *paths).split(b"\0")
    for name in names:
        if name:
            ref = ":" + name.decode("utf-8", errors="surrogateescape")
            if int(git("cat-file", "-s", ref)) > MAX_FILE_BYTES:
                raise ValueError("input_limit")
            yield git("show", ref)


def zip_blobs(path: str) -> Iterable[bytes]:
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > MAX_FILES:
            raise ValueError("input_limit")
        for item in members:
            name = item.filename.replace("\\", "/")
            if item.is_dir() or not any(name == allowed or name.endswith("/" + allowed) for allowed in ZIP_ALLOWLIST):
                continue
            if item.file_size > MAX_FILE_BYTES:
                raise ValueError("input_limit")
            with archive.open(item) as source:
                payload = source.read(MAX_FILE_BYTES + 1)
            if len(payload) > MAX_FILE_BYTES:
                raise ValueError("input_limit")
            yield payload


def path_blobs(paths: list[str]) -> Iterable[bytes]:
    for value in paths:
        path = Path(value)
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("invalid_path")
        with path.open("rb") as stream:
            yield stream.read(MAX_FILE_BYTES + 1)


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's normal error repeats attacker-controlled arguments/paths.
        raise ValueError("invalid_arguments")


def main(argv: list[str] | None = None) -> int:
    counts = dict.fromkeys(RULES, 0)
    report = {"schema_version": 1, "status": "incomplete", "files_scanned": 0, "rule_counts": counts, "coverage": "unselected"}
    try:
        parser = SafeParser(description=__doc__)
        modes = parser.add_mutually_exclusive_group()
        modes.add_argument("--source-zip")
        modes.add_argument("--staged", action="store_true")
        modes.add_argument("--tracked", action="store_true")
        parser.add_argument("--paths", nargs="+", default=[])
        args = parser.parse_args(argv)
        if args.source_zip and args.paths or not (args.source_zip or args.staged or args.tracked or args.paths):
            raise ValueError("invalid_arguments")
        report["coverage"] = "legacy_zip_credentials_allowlist" if args.source_zip else "git_index_text" if args.staged or args.tracked else "explicit_paths_text"
        if args.source_zip:
            report["allowlisted_members"] = list(ZIP_ALLOWLIST)
        blobs = zip_blobs(args.source_zip) if args.source_zip else git_blobs(args.staged, args.paths) if args.staged or args.tracked else path_blobs(args.paths)
        total = 0
        for blob in blobs:
            total += len(blob)
            if len(blob) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES or report["files_scanned"] >= MAX_FILES:
                raise ValueError("input_limit")
            # Binary assets are deliberately outside this text-secret scan.
            if b"\0" in blob:
                continue
            found = scan_text(blob.decode("utf-8", errors="replace"))
            for rule, count in found.items():
                counts[rule] += count
            report["files_scanned"] += 1
        report["status"] = "findings" if any(counts.values()) else "clean"
    except Exception:
        # Never serialize exception strings, file names, values or match context.
        report["status"] = "incomplete"
    print(json.dumps(report, sort_keys=True))
    return {"clean": 0, "findings": 1, "incomplete": 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
