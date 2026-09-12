"""Validate shared Plan A files without model calls or third-party dependencies."""
from pathlib import Path
import re
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def validate():
    config_path = ROOT / ".codex/config.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert set(config) == {"model", "model_reasoning_effort", "agents"}, "Unexpected project settings; review ownership before sharing"
    assert config["model"] == "gpt-6-astra" and config["model_reasoning_effort"] == "high", "Plan A primary must be Astra/high"
    defaults = config["agents"]
    assert defaults == {
        "enabled": True,
        "max_concurrent_threads_per_session": 3,
        "default_subagent_model": "gpt-5.6-terra",
        "default_subagent_reasoning_effort": "medium",
    }, "Unexpected Plan A subagent defaults"

    expected = {
        "rrn_scout": ("gpt-5.6-luna", "medium", True),
        "rrn_easy": ("gpt-5.6-luna", "low", False),
        "rrn_worker": ("gpt-5.6-terra", "medium", False),
        "rrn_architect": ("gpt-6-astra", "xhigh", True),
        "rrn_core": ("gpt-6-astra", "xhigh", False),
        "rrn_reviewer": ("gpt-6-astra", "high", True),
    }
    role_paths = sorted((ROOT / ".codex/agents").glob("rrn_*.toml"))
    assert {p.stem for p in role_paths} == set(expected), "Missing or unexpected RR-Nexus role"
    for path in role_paths:
        role = tomllib.loads(path.read_text(encoding="utf-8"))
        model, effort, readonly = expected[path.stem]
        allowed = {"name", "description", "model", "model_reasoning_effort", "developer_instructions", "sandbox_mode"}
        assert not set(role) - allowed, f"{path.name}: unexpected settings"
        assert role["name"] == path.stem, f"{path.name}: name mismatch"
        assert role["description"].strip() and role["developer_instructions"].strip(), f"{path.name}: missing instructions"
        assert (role["model"], role["model_reasoning_effort"]) == (model, effort), f"{path.name}: model/effort mismatch"
        assert role.get("sandbox_mode") == ("read-only" if readonly else None), f"{path.name}: permission inheritance mismatch"

    skill = ROOT / ".agents/skills/rrn-model-routing/SKILL.md"
    body = skill.read_text(encoding="utf-8")
    assert body.startswith("---\n"), "Skill frontmatter missing"
    frontmatter = body.split("---", 2)[1]
    assert re.search(r"^name: rrn-model-routing$", frontmatter, re.M), "Skill name mismatch"
    assert re.search(r"^description: .+", frontmatter, re.M), "Skill description missing"
    references = [skill.parent / p for p in re.findall(r"`(references/[^`]+\.md)`", body)]
    assert references and all(p.is_file() for p in references), "Broken skill references"
    shared = [config_path, *role_paths, skill, *references, ROOT / "docs/agent-routing/README.md"]
    assert all(p.is_file() for p in shared), "Shared file missing"
    for path in shared:
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", path.relative_to(ROOT).as_posix()],
            cwd=ROOT, capture_output=True, text=True,
        )
        assert result.returncode == 1, f"{path.relative_to(ROOT)} is ignored or Git check failed: {result.stderr}"
    print(f"PASS: Plan A config, {len(role_paths)} roles, skill references and {len(shared)} shared Git paths")
    print("Runtime schema acceptance, project trust and actual model calls require client verification.")


if __name__ == "__main__":
    if sys.flags.optimize:
        raise SystemExit("Run without -O: validation requires assertions.")
    try:
        validate()
    except (AssertionError, KeyError, TypeError, OSError, ValueError) as error:
        raise SystemExit(f"FAIL: {error}") from error
