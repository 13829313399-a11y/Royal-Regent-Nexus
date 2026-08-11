from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


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
    assert "HTTP redirect target does not match AI_PUBLIC_ORIGIN" in script
    assert "must remain active during preflight" in script
    assert "system_context_reservation=16384" in script
    assert "tool_schema_reservation=65536" in script
    assert "replay_factor * 8 * max_tool_result_bytes" in script
    assert "replay_factor * max_output_tokens" in script
