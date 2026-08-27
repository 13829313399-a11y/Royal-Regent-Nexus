from pathlib import Path

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
