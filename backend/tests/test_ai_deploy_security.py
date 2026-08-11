import ast
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _posix_shell() -> Path:
    candidates = [shutil.which("sh"), shutil.which("bash")]
    git = shutil.which("git")
    if git:
        candidates.append(
            str(Path(git).resolve().parent.parent / "bin" / "bash.exe")
        )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    pytest.skip("a POSIX shell is required for readiness parser verification")


def _shell_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name == "nt" and resolved.drive:
        suffix = resolved.as_posix().split(":", 1)[1].lstrip("/")
        return f"/{resolved.drive[0].lower()}/{suffix}"
    return str(resolved)


def test_deployment_backup_does_not_copy_runtime_secrets_or_full_inspect() -> None:
    script = (REPOSITORY_ROOT / "deploy" / "update-from-github.sh").read_text(
        encoding="utf-8"
    )

    assert 'cp "$ENV_FILE"' not in script
    assert "environment.snapshot" not in script
    assert "container-inspect" not in script
    assert 'docker inspect "$container_id" >' not in script
    assert 'docker inspect "$db_id" "$api_id" "$web_id" >' not in script
    assert "capture_environment_manifest" in script
    assert "capture_container_metadata" in script
    assert "environment.keys.txt" in script
    assert "environment.sha256" in script
    assert "ai_disable_marker_created" in script
    assert "AI Pilot is enabled; avoiding concurrent in-process limiter instances" in script
    assert "AI runtime disable marker remains active because deployment did not complete" in script
    assert "AI remains disabled by the runtime marker" in script
    assert '--volumes-from "$api_id"' in script
    assert script.count("--network none") >= 2
    assert "rm -f /control/ai.disabled" not in script


def test_pilot_readiness_script_checks_external_and_server_side_gates() -> None:
    script = (
        REPOSITORY_ROOT / "deploy" / "verify-ai-pilot-readiness.sh"
    ).read_text(encoding="utf-8")

    required_contracts = (
        "AI_PUBLIC_ORIGIN",
        "Strict-Transport-Security",
        "AI_PILOT_ENABLED",
        "AI_PILOT_USER_IDS",
        "AI_PILOT_FACTORY_IDS",
        "AI_PILOT_PUBLIC_TLS_VERIFIED",
        "AI_RUNTIME_DISABLE_PATH",
        "AI_PILOT_EXPECT_DISABLED_MARKER",
        "AI_PILOT_MAX_CONCURRENT_PER_USER",
        "AI_PILOT_REQUESTS_PER_MINUTE",
        "AI_PILOT_DAILY_TOKEN_BUDGET",
        "AI_PILOT_MAX_OUTPUT_TOKENS",
        "SESSION_COOKIE_SECURE",
        "AI_LOG_RAW_PROMPTS",
        "AI_LOG_RAW_TOOL_RESULTS",
        "/api/ai/capabilities",
        "/app/backend/control/ai.disabled",
    )
    for contract in required_contracts:
        assert contract in script

    assert "anonymous_status" in script
    assert '"$anonymous_status" = "401"' in script
    assert "require_env_csv_ids AI_PILOT_USER_IDS 128" in script
    assert "require_env_csv_ids AI_PILOT_FACTORY_IDS 6" in script
    assert "require_env_pilot_factories" in script
    assert "at most $maximum unique valid IDs" in script
    assert "AI_PILOT_FACTORY_IDS contains an unsupported factory ID" in script
    assert "HTTP redirect target does not match AI_PUBLIC_ORIGIN" in script
    assert "must remain active during preflight" in script
    assert "system_context_reservation=16384" in script
    assert "tool_schema_reservation=65536" in script
    assert "replay_factor * 8 * max_tool_result_bytes" in script
    assert "replay_factor * max_output_tokens" in script

    auth_tree = ast.parse(
        (REPOSITORY_ROOT / "backend" / "app" / "services" / "auth.py").read_text(
            encoding="utf-8"
        )
    )
    factory_ids: set[str] | None = None
    for node in auth_tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "ALLOWED_FACTORY_IDS"
            for target in node.targets
        ):
            factory_ids = ast.literal_eval(node.value)
            break
    assert factory_ids
    assert f"require_env_csv_ids AI_PILOT_FACTORY_IDS {len(factory_ids)}" in script
    for factory_id in factory_ids:
        assert f'allowed["{factory_id}"] = 1' in script


def test_pilot_readiness_csv_validation_executes_real_shell_boundaries(
    tmp_path: Path,
) -> None:
    script = (
        REPOSITORY_ROOT / "deploy" / "verify-ai-pilot-readiness.sh"
    ).read_text(encoding="utf-8")
    helper_start = script.index("fail() {")
    helper_end = script.index("require_env_integer_range() {")
    helpers = script[helper_start:helper_end]
    harness = tmp_path / "validate-ai-pilot-ids.sh"
    harness.write_text(
        "#!/usr/bin/env sh\n"
        "set -eu\n"
        "export LC_ALL=C\n"
        'ENV_FILE="$1"\n'
        f"{helpers}\n"
        "require_env_csv_ids AI_PILOT_USER_IDS 128\n"
        "require_env_csv_ids AI_PILOT_FACTORY_IDS 6\n"
        "require_env_pilot_factories\n",
        encoding="utf-8",
    )
    env_file = tmp_path / "pilot.env"
    shell = _posix_shell()
    canonical_factories = (
        "huakang-a,huakang-b,huakang-c,huakang-d,huadeng,huaxing"
    )

    def validate(users: str, factories: str = canonical_factories):
        env_file.write_text(
            f"AI_PILOT_USER_IDS={users}\n"
            f"AI_PILOT_FACTORY_IDS={factories}\n",
            encoding="utf-8",
        )
        return subprocess.run(
            [shell, _shell_path(harness), _shell_path(env_file)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    for count in (101, 128):
        users = ",".join(f"user-{index:03d}" for index in range(count))
        result = validate(f" , {users},,")
        assert result.returncode == 0, result.stderr

    invalid_lists = (
        ",".join(f"user-{index:03d}" for index in range(129)),
        "user-duplicate,user-duplicate",
        "user-valid,user invalid",
        f"user-valid,{'x' * 129}",
    )
    for users in invalid_lists:
        result = validate(users)
        assert result.returncode != 0
        assert "at most 128 unique valid IDs" in result.stderr
        assert users not in result.stderr

    invalid_factory = validate("user-valid", "huakang-a,unknown-factory")
    assert invalid_factory.returncode != 0
    assert "contains an unsupported factory ID" in invalid_factory.stderr
    assert "unknown-factory" not in invalid_factory.stderr
