from pathlib import Path
import os
import shutil
import subprocess

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "deploy" / "update-from-github.sh"
PROJECT_ROOT = SCRIPT_PATH.parents[1]


def test_deploy_script_tags_a_reachable_rollback_image() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'docker image inspect "$image_id"' in script
    assert 'docker tag "$image_id" "$rollback_tag"' in script
    assert "kind=tagged-existing-image" in script


def test_deploy_script_recovers_when_the_source_image_was_pruned() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'capture_container_metadata "$container_id" > "$metadata_path"' in script
    assert 'docker inspect "$container_id" >' not in script
    assert 'docker export "$container_id" > "$rootfs_path"' in script
    assert 'sha256sum "$rootfs_name" > "$rootfs_name.sha256"' in script
    assert 'sha256sum -c "$rootfs_name.sha256"' in script
    assert (
        'import_rootfs_rollback_image "$service_label" "$rootfs_path" "$rollback_tag"'
        in script
    )
    assert 'docker image inspect "$rollback_tag"' in script
    assert "kind=imported-rootfs-image" in script


def test_deploy_script_no_longer_tags_unchecked_container_image_ids() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'docker tag "$old_api_image"' not in script
    assert 'docker tag "$old_web_image"' not in script


def test_production_web_waits_for_a_healthy_api() -> None:
    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

    web_section = compose.split("\n  web:\n", maxsplit=1)[1].split(
        "\nvolumes:\n", maxsplit=1
    )[0]
    assert "condition: service_healthy" in web_section
    assert "condition: service_started" not in web_section


def test_web_healthcheck_covers_the_api_proxy_path() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")

    assert "wget --quiet --spider http://127.0.0.1/health" in dockerfile


def run_release_shell(code, directory, **env):
    shell = shutil.which("sh")
    if not shell and os.name == "nt" and shutil.which("git"):
        bundled_shell = Path(shutil.which("git")).resolve().parents[1] / "bin" / "sh.exe"
        if bundled_shell.is_file():
            shell = str(bundled_shell)
    if not shell:
        pytest.skip("release shell unavailable")
    return subprocess.run([shell, "-s"], input=code, text=True, cwd=directory,
                          capture_output=True, env={**os.environ, **env}, timeout=15)


@pytest.mark.parametrize(("notice", "outcome"), [
    ("1", "match"), ("1", "mismatch"), ("1", "http-error"), ("1", "signal"),
    ("0", "match"), ("0", "mismatch"), ("0", "http-error"), ("0", "superseded"),
])
def test_served_iam_failure_recloses_or_restores_web_only(tmp_path, notice, outcome):
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    functions = script.split('\ncd "$APP_DIR"\n', 1)[0]
    final_check = script.split("docker image prune -f >/dev/null\n", 1)[1].split('echo "Deployment completed', 1)[0]
    # Run the actual release finalization and cleanup. Stub Docker, the
    # HTTP client and the on-disk notice (its lock/state has separate tests).
    harness = r'''
mkdir receipts
backup_dir=receipts
printf 'new\n' > receipts/iam-web-candidate.txt
printf 'previous\n' > receipts/iam-web-before.txt
web_id=current
prior_project=production
[ "$MAINTENANCE_NOTICE_ENABLED" = 0 ] || { notice_id=ours; notice_entered=1; touch active; }
notice() {
    printf '%s\n' "$1" >> notices
    case "$1" in probe|complete) rm -f active;; fail) touch active;; esac
}
compose() {
    case "$*" in
        "ps -a -q web") if [ "$RESULT" = superseded ]; then echo another; else echo current; fi;;
        "ps -q web") echo restored;;
        *) return 42;;
    esac
}
docker() { printf '%s\n' "$*" >> docker-events; touch restored; }
wait_for_healthy() { [ "$1" = restored ]; }
python3() {
    if [ -f restored ]; then echo previous; return; fi
    case "$RESULT" in
        match) echo new;;
        http-error) echo unavailable >&2; return 1;;
        signal) kill -TERM "$$";;
        *) echo wrong;;
    esac
}
'''
    result = run_release_shell(functions + harness + final_check, tmp_path,
                               MAINTENANCE_NOTICE_ENABLED=notice, RESULT=outcome)
    assert (result.returncode == 0) == (outcome == "match"), result.stderr
    if notice == "1":
        assert (tmp_path / "notices").read_text().splitlines() == ["probe", "complete" if outcome == "match" else "fail"]
        assert (tmp_path / "active").exists() == (outcome != "match")
        assert not (tmp_path / "docker-events").exists()
    else:
        assert not (tmp_path / "notices").exists()
        if outcome in {"mismatch", "http-error"}:
            events = (tmp_path / "docker-events").read_text().splitlines()
            assert len(events) == 1 and events[0].endswith("up -d --no-deps --no-build --pull never web")
            assert (tmp_path / "receipts/iam-web-restored.txt").read_text().strip() == "previous"
        else:
            assert not (tmp_path / "docker-events").exists()
    if outcome == "http-error":
        assert "unavailable" in (tmp_path / "receipts/iam-web-served.txt.stderr").read_text()


@pytest.mark.parametrize(("config_files", "success"), [("compose.yml", True), ("compose.yml,private.yml", False)])
def test_no_notice_fallback_requires_original_compose_stack(tmp_path, config_files, success):
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    functions = script.split('\ncd "$APP_DIR"\n', 1)[0]
    check = script.split('|| fail "Production HEAD cannot be fast-forwarded to $UPSTREAM"\n', 1)[1].split('\ntimestamp=', 1)[0]
    harness = r'''
APP_DIR="$PWD"
COMPOSE_FILE=compose.yml
touch "$COMPOSE_FILE"
web_id=original
docker() {
    case "$*" in *working_dir*) echo "$PWD";; *) echo "$PWD/$STACK";; esac
}
'''
    result = run_release_shell(functions + harness + check, tmp_path, MAINTENANCE_NOTICE_ENABLED="0", STACK=config_files)
    assert (result.returncode == 0) == success, result.stderr
