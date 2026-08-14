import ast
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_ai_prompt_runtime_assets_are_complete_and_git_tracked() -> None:
    prompt_root = REPOSITORY_ROOT / "backend" / "app" / "services" / "ai" / "prompts"
    manifest_root = prompt_root.parent / "skills" / "manifests"
    manifest_ids = {
        yaml.safe_load(path.read_text(encoding="utf-8"))["id"]
        for path in manifest_root.glob("*.yaml")
    }
    assert manifest_ids

    runtime_assets = {
        prompt_root / "core_policy.md",
        *(prompt_root / "skills" / f"{skill_id}.md" for skill_id in manifest_ids),
    }
    fixture_assets = {
        REPOSITORY_ROOT
        / "backend"
        / "tests"
        / "fixtures"
        / "ai_task_skill"
        / "prompts"
        / "core_policy.md",
        REPOSITORY_ROOT
        / "backend"
        / "tests"
        / "fixtures"
        / "ai_task_skill"
        / "prompts"
        / "skills"
        / "test.fake_task.md",
    }
    required_assets = runtime_assets | fixture_assets
    missing = sorted(
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in required_assets
        if not path.is_file()
    )
    assert not missing, f"missing AI Prompt assets: {missing}"

    actual_runtime_assets = set((prompt_root / "skills").glob("*.md"))
    assert actual_runtime_assets == runtime_assets - {prompt_root / "core_policy.md"}

    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", *sorted(
            path.relative_to(REPOSITORY_ROOT).as_posix()
            for path in required_assets
        )],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    tracked_paths = {path for path in tracked if path}
    required_paths = {
        path.relative_to(REPOSITORY_ROOT).as_posix() for path in required_assets
    }
    assert tracked_paths == required_paths, (
        "AI Prompt assets must be committed so clean archives and production images "
        f"contain them; untracked={sorted(required_paths - tracked_paths)}"
    )

    dockerfile = (REPOSITORY_ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    assert "build_default_tool_registry(document_studio_enabled=True)" in dockerfile
    assert "registry.prompt_registry.load_core()" in dockerfile

    production_requirements = {
        line.strip()
        for line in (
            REPOSITORY_ROOT / "backend" / "requirements.prod.txt"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "httpx2==2.9.0" in production_requirements


def test_ai_knowledge_runtime_assets_are_packaged() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile.backend").read_text(encoding="utf-8")

    assert "COPY docs/ai/ /app/docs/ai/" in dockerfile
    assert "COPY src/ /app/src/" in dockerfile


def test_ai_task_worker_has_a_process_specific_healthcheck() -> None:
    compose = yaml.safe_load(
        (REPOSITORY_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    )

    healthcheck = compose["services"]["ai-task-worker"]["healthcheck"]
    assert healthcheck["test"][:3] == ["CMD", "python", "-c"]
    assert "app.services.ai.task_worker" in healthcheck["test"][3]


def _posix_shell() -> Path:
    candidates = [shutil.which("sh"), shutil.which("bash")]
    git = shutil.which("git")
    if git:
        candidates.append(str(Path(git).resolve().parent.parent / "bin" / "bash.exe"))
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
    assert (
        "AI runtime disable marker remains active because deployment did not complete"
        in script
    )
    assert "AI remains disabled by the runtime marker" in script
    assert (
        'ai_shared_guard_enabled="$(read_env_value AI_SHARED_GUARD_ENABLED)"' in script
    )
    assert (
        "Shared AI Guard enabled; starting the candidate behind the active AI disable marker"
        in script
    )
    assert (
        "AI Pilot is enabled without Shared Guard; avoiding concurrent limiter instances"
        in script
    )
    assert '--volumes-from "$api_id"' in script
    assert script.count("--network none") >= 2
    assert "rm -f /control/ai.disabled" not in script


def test_pilot_readiness_script_checks_external_and_server_side_gates() -> None:
    script = (REPOSITORY_ROOT / "deploy" / "verify-ai-pilot-readiness.sh").read_text(
        encoding="utf-8"
    )

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
        "AI_NIF18_STAGE",
        "AI_OPERATIONAL_ALERTS_ENABLED",
        "AI_ALERT_TARGET_USER_IDS",
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
    assert "require_env_exact AI_SHARED_GUARD_ENABLED true" in script
    assert "require_env_exact AI_TASK_WORKER_ENABLED true" in script
    assert "require_env_exact AI_ARTIFACT_SCANNER_BACKEND clamav" in script
    assert "require_env_exact AI_FEEDBACK_ENABLED true" in script
    assert "require_env_exact AI_OBSERVABILITY_ENABLED true" in script
    assert "require_env_positive_decimal AI_INPUT_TOKEN_COST_USD_PER_MILLION" in script
    assert "require_env_exact AI_OPERATIONAL_ALERTS_ENABLED true" in script
    assert "require_env_csv_ids AI_ALERT_TARGET_USER_IDS 16 64" in script
    assert (
        "require_env_integer_range AI_COST_PER_SUCCESSFUL_TASK_ALERT_MICROUSD 1 10000000000"
        in script
    )
    assert "require_env_integer_range AI_BUDGET_ALERT_PERCENT 1 100" in script
    assert "database revision does not match the single code head" in script
    assert "AI_ACTION_GATEWAY_ENABLED false" in script
    assert "AI_ACTION_GATEWAY_ENABLED true" in script
    assert "AI_CONTROLLED_APPLY_ENABLED false" in script
    assert "AI_CONTROLLED_APPLY_ENABLED true" in script

    production_example = (REPOSITORY_ROOT / ".env.production.example").read_text(
        encoding="utf-8"
    )
    backend_example = (
        REPOSITORY_ROOT / "backend" / ".env.example"
    ).read_text(encoding="utf-8")
    assert "AI_ACTION_GATEWAY_ENABLED=false" in production_example
    assert "AI_ACTION_GATEWAY_ENABLED=false" in backend_example
    assert "AI_OPERATIONAL_ALERTS_ENABLED=false" in production_example
    assert "AI_OPERATIONAL_ALERTS_ENABLED=false" in backend_example

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


def test_nif18_evidence_verifier_requires_every_field_gate() -> None:
    verifier = (REPOSITORY_ROOT / "deploy" / "verify-ai-nif18-evidence.sh").read_text(
        encoding="utf-8"
    )
    template = (
        REPOSITORY_ROOT / "deploy" / "nif18-production-evidence.template"
    ).read_text(encoding="utf-8")

    required_gates = (
        "GIT_GATE",
        "MIGRATION_GATE",
        "TLS_HSTS_GATE",
        "SESSION_GATE",
        "SECRET_ROTATION_GATE",
        "IAM_PILOT_GATE",
        "PROVIDER_REGION_GATE",
        "SHARED_GUARD_GATE",
        "MULTI_INSTANCE_GATE",
        "KILL_SWITCH_GATE",
        "PROVIDER_FAULT_GATE",
        "WORKER_RECOVERY_GATE",
        "DATABASE_BACKUP_RESTORE_GATE",
        "ARTIFACT_OPERATIONS_GATE",
        "EVIDENCE_REAUTH_GATE",
        "CONTROLLED_APPLY_DRAFT_GATE",
        "BUSINESS_FAILURE_ISOLATION_GATE",
        "BROWSER_ACCEPTANCE_GATE",
        "ROLLBACK_GATE",
        "COST_ALERT_GATE",
        "COST_PER_SUCCESSFUL_TASK_ALERT_GATE",
        "PROVIDER_FAILURE_ALERT_GATE",
        "TOOL_FAILURE_ALERT_GATE",
        "WORKER_RECOVERY_ALERT_GATE",
        "SCANNER_STALE_ALERT_GATE",
        "BUDGET_ALERT_GATE",
        "ALERT_ACKNOWLEDGEMENT_GATE",
    )
    for gate in required_gates:
        assert gate in verifier
        assert f"{gate}=PENDING" in template
    assert "git status --porcelain --untracked-files=no" in verifier
    assert "git merge-base --is-ancestor" in verifier
    assert "credentials or cookies" in verifier
    assert "CONTROLLED_APPLY_DRAFT_GATE=PENDING" in template


def test_nif18_kill_switch_drill_is_explicit_one_way_and_secret_safe() -> None:
    script = (
        REPOSITORY_ROOT / "deploy" / "run-ai-nif18-kill-switch-drill.sh"
    ).read_text(encoding="utf-8")

    assert "DISABLE_AI_AND_VERIFY_BUSINESS" in script
    assert "AI_DRILL_COOKIE_FILE" in script
    assert '--network none -v "$api_volume:/control"' in script
    assert ": > /control/ai.disabled" in script
    assert '"AI_DISABLED"' in script
    assert '"status"[[:space:]]*:[[:space:]]*"ok"' in script
    assert "API and Worker do not share the runtime control volume" in script
    assert "rm -f /control/ai.disabled" not in script
    assert '--cookie "$COOKIE_FILE"' in script
    assert 'cat "$COOKIE_FILE"' not in script


def test_nif18_evidence_template_and_runbook_remain_no_go() -> None:
    runbook = (
        REPOSITORY_ROOT / "docs" / "ai" / "nif-18-production-readiness.md"
    ).read_text(encoding="utf-8")
    assert "`NO-GO`" in runbook
    assert "ADR-012" in runbook
    assert "ADR-012 is `ACCEPTED`" in runbook
    assert "has not received `FIELD-PASS`" in runbook
    assert "不会" not in runbook  # evidence wording stays operational and testable
    assert "never put credentials" in (
        REPOSITORY_ROOT / "deploy" / "nif18-production-evidence.template"
    ).read_text(encoding="utf-8")


def test_nif18_evidence_verifier_executes_strict_boundaries(tmp_path: Path) -> None:
    shell = _posix_shell()
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "nif18@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "NIF18 Test"], cwd=repository, check=True
    )
    (repository / "baseline.txt").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "baseline.txt"], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "baseline"], cwd=repository, check=True
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", revision],
        cwd=repository,
        check=True,
    )
    verifier = REPOSITORY_ROOT / "deploy" / "verify-ai-nif18-evidence.sh"
    evidence = tmp_path / "nif18.evidence"
    gates = (
        "GIT_GATE",
        "MIGRATION_GATE",
        "TLS_HSTS_GATE",
        "SESSION_GATE",
        "SECRET_ROTATION_GATE",
        "IAM_PILOT_GATE",
        "PROVIDER_REGION_GATE",
        "SHARED_GUARD_GATE",
        "MULTI_INSTANCE_GATE",
        "KILL_SWITCH_GATE",
        "PROVIDER_FAULT_GATE",
        "WORKER_RECOVERY_GATE",
        "DATABASE_BACKUP_RESTORE_GATE",
        "ARTIFACT_OPERATIONS_GATE",
        "EVIDENCE_REAUTH_GATE",
        "CONTROLLED_APPLY_DRAFT_GATE",
        "BUSINESS_FAILURE_ISOLATION_GATE",
        "BROWSER_ACCEPTANCE_GATE",
        "ROLLBACK_GATE",
        "COST_ALERT_GATE",
        "COST_PER_SUCCESSFUL_TASK_ALERT_GATE",
        "PROVIDER_FAILURE_ALERT_GATE",
        "TOOL_FAILURE_ALERT_GATE",
        "WORKER_RECOVERY_ALERT_GATE",
        "SCANNER_STALE_ALERT_GATE",
        "BUDGET_ALERT_GATE",
        "ALERT_ACKNOWLEDGEMENT_GATE",
    )
    references = (
        "PILOT_USER_SET_REF",
        "PILOT_FACTORY_SET_REF",
        "BACKUP_EVIDENCE_REF",
        "RESTORE_DRILL_REF",
        "FAULT_DRILL_REF",
        "BROWSER_EVIDENCE_REF",
        "COST_ALERT_REF",
        "COST_PER_SUCCESSFUL_TASK_ALERT_REF",
        "PROVIDER_FAILURE_ALERT_REF",
        "TOOL_FAILURE_ALERT_REF",
        "WORKER_RECOVERY_ALERT_REF",
        "SCANNER_STALE_ALERT_REF",
        "BUDGET_ALERT_REF",
        "ALERT_ACKNOWLEDGEMENT_REF",
        "PRODUCT_APPROVER",
        "SECURITY_APPROVER",
        "OPERATIONS_APPROVER",
    )
    evidence.write_text(
        "NIF18_SCHEMA_VERSION=nif18-production-evidence-v2\n"
        "OVERALL_RESULT=PASS\n"
        f"DEPLOYED_REVISION={revision}\n"
        "EXECUTED_AT_UTC=2026-08-13T00:00:00Z\n"
        + "".join(f"{gate}=PASS\n" for gate in gates)
        + "".join(
            f"{field}=evidence-{index}\n" for index, field in enumerate(references)
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["NIF18_EVIDENCE_FILE"] = _shell_path(evidence)
    env["UPSTREAM_REF"] = "origin/main"
    passed = subprocess.run(
        [shell, _shell_path(verifier)],
        cwd=repository,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert passed.returncode == 0, passed.stderr
    assert revision in passed.stdout

    evidence.write_text(
        evidence.read_text(encoding="utf-8").replace(
            "CONTROLLED_APPLY_DRAFT_GATE=PASS",
            "CONTROLLED_APPLY_DRAFT_GATE=PENDING",
        ),
        encoding="utf-8",
    )
    pending = subprocess.run(
        [shell, _shell_path(verifier)],
        cwd=repository,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert pending.returncode != 0
    assert "CONTROLLED_APPLY_DRAFT_GATE" in pending.stderr

    evidence.write_text(
        evidence.read_text(encoding="utf-8")
        .replace(
            "CONTROLLED_APPLY_DRAFT_GATE=PENDING",
            "CONTROLLED_APPLY_DRAFT_GATE=PASS",
        )
        .replace(
            "PROVIDER_FAILURE_ALERT_REF=evidence-8",
            "PROVIDER_FAILURE_ALERT_REF=evidence-7",
        ),
        encoding="utf-8",
    )
    duplicate_alert_reference = subprocess.run(
        [shell, _shell_path(verifier)],
        cwd=repository,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert duplicate_alert_reference.returncode != 0
    assert "duplicates the evidence reference" in duplicate_alert_reference.stderr

    evidence.write_text(
        evidence.read_text(encoding="utf-8")
        .replace(
            "PROVIDER_FAILURE_ALERT_REF=evidence-7",
            "PROVIDER_FAILURE_ALERT_REF=evidence-8",
        )
        + "BUDGET_ALERT_GATE=PASS\n",
        encoding="utf-8",
    )
    duplicate_key = subprocess.run(
        [shell, _shell_path(verifier)],
        cwd=repository,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert duplicate_key.returncode != 0
    assert "duplicate evidence key: BUDGET_ALERT_GATE" in duplicate_key.stderr


def test_pilot_readiness_csv_validation_executes_real_shell_boundaries(
    tmp_path: Path,
) -> None:
    script = (REPOSITORY_ROOT / "deploy" / "verify-ai-pilot-readiness.sh").read_text(
        encoding="utf-8"
    )
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
    canonical_factories = "huakang-a,huakang-b,huakang-c,huakang-d,huadeng,huaxing"

    def validate(users: str, factories: str = canonical_factories):
        env_file.write_text(
            f"AI_PILOT_USER_IDS={users}\nAI_PILOT_FACTORY_IDS={factories}\n",
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
