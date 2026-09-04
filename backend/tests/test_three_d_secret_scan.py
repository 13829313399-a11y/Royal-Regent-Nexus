import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan_three_d_secrets.py"
SPEC = importlib.util.spec_from_file_location("secret_scan", SCRIPT)
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)
SENTINEL = "NeverEmit" + "SensitiveSentinel93824"


@pytest.mark.parametrize("key", ["accesscode", "AccessCode", "ACCESS_CODE", "lan_access_code", "PrinterAccessCode"])
def test_access_code_case_variants(key):
    assert scanner.scan_text(json.dumps({key: SENTINEL}))["device_access_code"] == 1


def test_safe_placeholders_and_runtime_reference():
    for placeholder in ("<REDACTED>", "${PRINTER_ACCESS_CODE}", "replace-me", "replace-locally", "test-access-code", ""):
        assert not any(scanner.scan_text(json.dumps({"accesscode": placeholder})).values())
    assert not any(scanner.scan_text('access_code = os.getenv("PRINTER_ACCESS_CODE")').values())
    assert not any(scanner.scan_text("ACCESS_CODE=${PRINTER_ACCESS_CODE}").values())


def test_plain_env_and_wireguard_key():
    assert scanner.scan_text("PRINTER_ACCESS_" + "CODE=" + SENTINEL)["device_access_code"] == 1
    assert scanner.scan_text("PrivateKey=" + "a" * 43 + "=")["private_key"] == 1


def test_pat_url_private_key_and_basic_auth():
    assert scanner.scan_text("gh" + "p_" + "a1B2" * 9)["github_token"] == 1
    assert scanner.scan_text("https://user:" + SENTINEL + "@example.invalid/repo")["url_credentials"] == 1
    assert scanner.scan_text("-----BEGIN " + "OPENSSH PRIVATE KEY-----")["private_key"] == 1
    assert scanner.scan_text(json.dumps({"BasicAuth": {"Password": SENTINEL}}))["basic_auth"] == 1
    assert scanner.scan_text('BASIC_AUTH_PASSWORD = "' + SENTINEL + '"')["basic_auth"] == 1
    assert scanner.scan_text("Authorization: " + "Basic " + "dXNlcjpwYXNz")["basic_auth"] == 1


def test_zip_and_output_never_reveal_names_or_secrets(tmp_path, capsys):
    source = tmp_path / (SENTINEL + ".zip")
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(SENTINEL + "/.git/config", "url=https://user:" + SENTINEL + "@example.invalid/repo")
        archive.writestr("../" + SENTINEL + "/config.json", json.dumps({"AccessCode": SENTINEL, "basicAuth": {"password": SENTINEL}}))
        archive.writestr("do-not-execute.py", 'raise RuntimeError("must not execute")')
    assert scanner.main(["--source-zip", str(source)]) == 1
    output = capsys.readouterr()
    assert SENTINEL not in output.out + output.err
    report = json.loads(output.out)
    assert report["status"] == "findings"
    assert report["rule_counts"]["url_credentials"] == 1
    assert report["rule_counts"]["device_access_code"] == 1
    assert report["rule_counts"]["basic_auth"] == 1
    assert list(tmp_path.iterdir()) == [source]


def test_zip_excludes_business_data_before_size_check(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("project/config.json", "{}")
        for name in ("data.json", "data.sqlite", "image.png", "business.py"):
            archive.writestr("project/" + name, SENTINEL * 10)
    monkeypatch.setattr(scanner, "MAX_FILE_BYTES", 3)
    assert scanner.main(["--source-zip", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["files_scanned"] == 1
    assert report["coverage"] == "legacy_zip_credentials_allowlist"
    assert report["allowlisted_members"] == list(scanner.ZIP_ALLOWLIST)


def test_incomplete_overrides_existing_findings(tmp_path, capsys):
    source = tmp_path / "config.json"
    source.write_text(json.dumps({"accesscode": SENTINEL}))
    assert scanner.main(["--paths", str(source), str(tmp_path / "missing")]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "incomplete"
    assert report["rule_counts"]["device_access_code"] == 1
    result = subprocess.run([sys.executable, str(SCRIPT), "--paths", str(source), str(tmp_path / "missing")], capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "incomplete"
    assert SENTINEL not in result.stdout + result.stderr


@pytest.mark.parametrize("args", [["--unknown", SENTINEL], ["--paths", SENTINEL], ["--source-zip", SENTINEL]])
def test_failures_do_not_reveal_input(args, capsys):
    assert scanner.main(args) == 2
    result = capsys.readouterr()
    assert SENTINEL not in result.out + result.err
    assert json.loads(result.out)["status"] == "incomplete"


def test_limits_fail_closed(tmp_path, monkeypatch, capsys):
    source = tmp_path / "large.json"
    source.write_text("x" * 11)
    monkeypatch.setattr(scanner, "MAX_FILE_BYTES", 10)
    assert scanner.main(["--paths", str(source)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "incomplete"


def test_git_modes_read_index_and_respect_paths(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, check=True)

    git("init")
    source = tmp_path / "config.json"
    source.write_text(json.dumps({"accesscode": SENTINEL}))
    (tmp_path / "safe.md").write_text("safe")
    git("add", "config.json", "safe.md")
    source.write_text("{}")
    for mode in ("--staged", "--tracked"):
        result = subprocess.run([sys.executable, str(SCRIPT), mode], cwd=tmp_path, capture_output=True, text=True)
        assert result.returncode == 1
        assert SENTINEL not in result.stdout + result.stderr
        result = subprocess.run([sys.executable, str(SCRIPT), mode, "--paths", "safe.md"], cwd=tmp_path, capture_output=True, text=True)
        assert result.returncode == 0
