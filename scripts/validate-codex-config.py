"""Read-only V2 policy checks; not an official schema or runtime/model test."""
from pathlib import Path
import re
import subprocess
import sys

try:
    import tomllib
except ImportError:
    tomllib = None

ROOT = Path(__file__).resolve().parents[1]
SYNTAX = "STATIC_SYNTAX"
POLICY = "POLICY_CONSISTENCY"
RUNTIME = "RUNTIME_UNVERIFIED"
ROLES = {
    "rrn_scout": ("gpt-5.6-luna", "medium", True),
    "rrn_easy": ("gpt-5.6-luna", "low", False),
    "rrn_worker": ("gpt-5.6-terra", "medium", False),
    "rrn_architect": ("gpt-6-astra", "high", True),
    "rrn_core": ("gpt-6-astra", "high", False),
    "rrn_reviewer": ("gpt-6-astra", "high", True),
}
DEFAULTS = {
    "model": "gpt-5.6-terra",
    "model_reasoning_effort": "medium",
    "plan_mode_reasoning_effort": "medium",
}
AGENTS = {
    "enabled": True,
    "max_concurrent_threads_per_session": 1,
    "default_subagent_model": "gpt-5.6-terra",
    "default_subagent_reasoning_effort": "medium",
}
SKILL = ".agents/skills/rrn-model-routing/SKILL.md"
DOCS = (
    "AGENTS.md", "PROJECT_MEMORY.md", SKILL,
    ".agents/skills/rrn-model-routing/references/task-routing.md",
    ".agents/skills/rrn-model-routing/references/repo-map.md",
    "docs/agent-routing/README.md", "docs/agent-routing/context-index.md",
    "docs/agent-routing/validation.md",
)
LOCAL_PATHS = (
    ".tmp/agent-routing/probe.jsonl", ".tmp/agent-routing/notes.md",
    ".codex/auth.json", ".codex/session.jsonl", ".codex/local.config.toml",
    ".codex/agents/local-private.toml",
)


def git_ignored(root, path):
    """Git exit 1 means visible, 0 ignored; all other results are errors."""
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", "--", path],
        cwd=root, capture_output=True, text=True, timeout=15,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Git check failed ({result.returncode}): {result.stderr.strip()}")
    return result.returncode == 0


def validate(root=ROOT):
    """Return categorized evidence, never mutate inputs or call models."""
    root = Path(root).resolve()
    report = {"errors": {SYNTAX: [], POLICY: []}, "warnings": [],
              RUNTIME: "App loading, actual model/effort, sandbox, child tools and usage are unverified."}

    def fail(category, path, message):
        report["errors"][category].append(f"{path}: {message}")

    def read(path):
        try:
            return (root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            fail(SYNTAX, path, str(error))
            return None

    if tomllib is None:
        fail(SYNTAX, "Python", "Use an existing Python 3.11+ environment (tomllib required); no installation performed.")
        return report

    def toml(path):
        body = read(path)
        if body is None:
            return {}
        try:
            return tomllib.loads(body)
        except tomllib.TOMLDecodeError as error:
            fail(SYNTAX, path, str(error))
            return {}

    def fields(data, expected, path):
        if not isinstance(data, dict):
            fail(SYNTAX, path, "expected a TOML table")
            return
        for key, target in expected.items():
            if key not in data:
                fail(SYNTAX, path, f"missing {key}")
            elif type(data[key]) is not type(target):
                fail(SYNTAX, path, f"{key}: invalid type; expected {type(target).__name__}")
            elif data[key] != target:
                fail(POLICY, path, f"{key}: V2 requires {target!r}, got {data[key]!r}")

    def extras(data, allowed, path):
        if isinstance(data, dict):
            unknown = set(data) - set(allowed)
            if unknown:
                report["warnings"].append(f"{path}: additional fields {', '.join(sorted(unknown))}; not checked against official schema; preserved.")

    config_path = ".codex/config.toml"
    config = toml(config_path)
    fields(config, DEFAULTS, config_path)
    fields(config.get("agents", {}), AGENTS, config_path + " [agents]")
    extras(config, {*DEFAULTS, "agents"}, config_path)
    extras(config.get("agents"), AGENTS, config_path + " [agents]")
    for key in ("profiles", "profile", "budget_tokens", "daily_budget", "auto_router", "max_total_agents"):
        if key in config:
            fail(POLICY, config_path, f"{key}: not a supported V2 project routing mechanism")
    if isinstance(config.get("agents"), dict):
        for key in ("max_depth", "max_total_agents", "budget_tokens", "daily_budget", "auto_router", "max_threads"):
            if key in config["agents"]:
                fail(POLICY, config_path, f"agents.{key}: conflicts with canonical V2 ownership; verify instead of inventing a limit")
    if config.get("service_tier") == "standard":
        fail(POLICY, config_path, "service_tier='standard' is not the V2 supported-entry policy")

    paths = sorted((root / ".codex/agents").glob("*.toml"))
    actual = {p.stem for p in paths if p.stem.startswith("rrn_")}
    if actual != set(ROLES):
        fail(SYNTAX, ".codex/agents", f"role paths differ: missing {sorted(set(ROLES)-actual)}, unexpected {sorted(actual-set(ROLES))}")
    names = {}
    role_paths = []
    for p in paths:
        path = p.relative_to(root).as_posix()
        role = toml(path)
        for key in ("name", "description", "developer_instructions"):
            if not isinstance(role.get(key), str) or not role[key].strip():
                fail(SYNTAX, path, f"missing/non-string/empty {key}")
        name = role.get("name")
        if isinstance(name, str):
            if name in names:
                fail(SYNTAX, path, f"duplicate role name {name!r}; first defined in {names[name]}")
            names[name] = path
        if p.stem not in ROLES:
            continue  # Do not impose RR naming/model policy on unrelated roles.
        role_paths.append(path)
        if name != p.stem:
            fail(SYNTAX, path, "name must match canonical RR filename")
        model, effort, readonly = ROLES[p.stem]
        fields(role, {"model": model, "model_reasoning_effort": effort}, path)
        fields(role.get("agents", {}), {"enabled": False}, path + " [agents]")
        if readonly and role.get("sandbox_mode") != "read-only":
            fail(POLICY, path, "read-only declaration required")
        if not readonly and "sandbox_mode" in role:
            fail(POLICY, path, "write roles must inherit existing permissions; no sandbox override")
        instructions = role.get("developer_instructions", "")
        if isinstance(instructions, str) and "不要继续派生子代理" not in instructions:
            fail(POLICY, path, "missing no-child-delegation instruction")
        extras(role, {"name", "description", "developer_instructions", "model", "model_reasoning_effort", "sandbox_mode", "agents"}, path)
        extras(role.get("agents"), {"enabled"}, path + " [agents]")

    bodies = {path: read(path) for path in DOCS}
    skill = bodies.get(SKILL) or ""
    frontmatter = re.match(r"\A---\n(.*?)\n---(?:\n|$)", skill, re.S)
    if not frontmatter:
        fail(SYNTAX, SKILL, "skill frontmatter missing or unterminated")
    else:
        front = frontmatter.group(1)
        if not re.search(r"^name: rrn-model-routing\s*$", front, re.M):
            fail(SYNTAX, SKILL, "skill name mismatch")
        if not re.search(r"^description: [^\n\S]*\S[^\n]*$", front, re.M):
            fail(SYNTAX, SKILL, "skill description missing")

    references = re.findall(r"`(references/[^`]+\.md)`", skill)
    if not references:
        fail(SYNTAX, SKILL, "no reference paths")
    shared = {config_path, *role_paths, *DOCS,
              "scripts/validate-codex-config.py", "scripts/tests/test_codex_config.py"}

    def reference(source, target):
        p = (root / source).parent / target
        p = p.resolve()
        if not p.is_relative_to(root):
            fail(SYNTAX, source, f"reference escapes repository: {target}")
        elif not p.is_file():
            fail(SYNTAX, source, f"broken reference: {target}")
        else:
            shared.add(p.relative_to(root).as_posix())

    for target in references:
        reference(SKILL, target)
    for path, body in bodies.items():
        if body is None:
            continue
        # Business memory is intentionally not re-audited as an unrelated doc graph.
        if path != "PROJECT_MEMORY.md":
            for target in re.findall(r"\[[^\]\n]+\]\(([^)\s]+)\)", body):
                if not re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) and not target.startswith("#"):
                    reference(path, target.split("#", 1)[0])

    # Detect known superseded ACTIVE defaults, not all historical/model mentions.
    active = ["AGENTS.md", SKILL, ".agents/skills/rrn-model-routing/references/task-routing.md", "docs/agent-routing/README.md"]
    stale = (
        r"(?im)^#{1,6} .*?(?:Plan A|质量优先方案\s*A)",
        r"(?i)(?:日常|daily|primary|主线程|主代理).{0,24}(?:默认|default).{0,16}(?:Astra|gpt-6-astra)",
        r"(?i)(?:Astra/high leads|quality-first Plan A|采用质量优先方案 A)",
        r"(?:通常只需要零至两个子代理|上限为三个|configured maximum is three)",
        r"(?im)^\|[^\n]*(?:rrn_core|rrn_architect)[^\n]*xhigh[^\n]*\|$",
    )
    for path in active:
        body = bodies.get(path) or ""
        for pattern in stale:
            if re.search(pattern, body):
                fail(POLICY, path, "superseded active default detected; reconcile V2 rules")
    memory = bodies.get("PROJECT_MEMORY.md") or ""
    for line in memory.splitlines():
        if "Repository-owned Codex development defaults" in line and "Plan A" in line:
            fail(POLICY, "PROJECT_MEMORY.md", "canonical Codex default still uses Plan A")

    for path in sorted(shared):
        if not (root / path).is_file():
            fail(SYNTAX, path, "shared file missing")
        try:
            if git_ignored(root, path):
                fail(POLICY, path, "shared file is Git-ignored; fix a precise allow rule")
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            fail(POLICY, path, str(error))
            break
    for path in LOCAL_PATHS:
        try:
            if not git_ignored(root, path):
                fail(POLICY, path, "local state is not Git-ignored; fix a local ignore rule, do not expose all .codex")
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            fail(POLICY, path, str(error))
            break
    for path in ("AGENTS.md", SKILL):
        body = bodies.get(path)
        if body is not None:
            try:
                size = (root / path).stat().st_size
                report["warnings"].append(f"SIZE: {path}: {size} bytes, not a token count or hard cap")
            except OSError as error:
                fail(SYNTAX, path, str(error))
    return report


def main():
    report = validate()
    for category in (SYNTAX, POLICY):
        errors = report["errors"][category]
        print(f"{category}: {'FAIL' if errors else 'PASS'}")
        for error in errors:
            print(f"  {error}")
    for warning in report["warnings"]:
        print(f"NOTE: {warning}")
    print(f"{RUNTIME}: {report[RUNTIME]}")
    return int(any(report["errors"].values()))


if __name__ == "__main__":
    # Explicit checks, not assert: optimization does not bypass validation.
    raise SystemExit(main())
