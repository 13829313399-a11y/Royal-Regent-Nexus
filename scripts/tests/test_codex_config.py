"""Deterministic V2 fixtures; no model calls, credentials or real config writes."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "validate-codex-config.py"
spec = importlib.util.spec_from_file_location("codex_config", SCRIPT)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put(".codex/config.toml", '''model = "gpt-5.6-terra"
model_reasoning_effort = "medium"
plan_mode_reasoning_effort = "medium"
[agents]
enabled = true
max_concurrent_threads_per_session = 1
default_subagent_model = "gpt-5.6-terra"
default_subagent_reasoning_effort = "medium"
''')
        for name, model, effort, readonly in (
            ("rrn_scout", "gpt-5.6-luna", "medium", True),
            ("rrn_easy", "gpt-5.6-luna", "low", False),
            ("rrn_worker", "gpt-5.6-terra", "medium", False),
            ("rrn_architect", "gpt-6-astra", "high", True),
            ("rrn_core", "gpt-6-astra", "high", False),
            ("rrn_reviewer", "gpt-6-astra", "high", True),
        ):
            sandbox = 'sandbox_mode = "read-only"\n' if readonly else ""
            self.put(f".codex/agents/{name}.toml", f'''name = "{name}"
description = "A bounded role"
model = "{model}"
model_reasoning_effort = "{effort}"
{sandbox}developer_instructions = "不要继续派生子代理。"
[agents]
enabled = false
''')
        for path in validator.DOCS:
            self.put(path, "# V2\nDaily default: Terra/medium.\n")
        self.put(validator.SKILL, '''---
name: rrn-model-routing
description: Nontrivial routing only.
---
# V2
`references/task-routing.md`
`references/repo-map.md`
''')
        self.put("scripts/validate-codex-config.py", SCRIPT.read_text(encoding="utf-8"))
        self.put("scripts/tests/test_codex_config.py", "# fixture\n")
        self.put(".gitignore", '''.tmp/
.codex/*
!.codex/config.toml
!.codex/agents/
.codex/agents/*
!.codex/agents/rrn_*.toml
''')

    def put(self, path, body):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def change(self, path, old, new):
        p = self.root / path
        body = p.read_text(encoding="utf-8")
        self.assertIn(old, body)
        p.write_text(body.replace(old, new), encoding="utf-8")

    def check(self):
        with patch.object(validator, "git_ignored", side_effect=lambda root, p: p in validator.LOCAL_PATHS):
            return validator.validate(self.root)

    def fails(self, text, category=None):
        report = self.check()
        errors = report["errors"]
        messages = errors[category] if category else sum(errors.values(), [])
        self.assertTrue(messages, report)
        self.assertIn(text, "\n".join(messages))

    def test_valid_v2_is_still_runtime_unverified(self):
        report = self.check()
        self.assertFalse(any(report["errors"].values()), report)
        self.assertIn("unverified", report[validator.RUNTIME])

    def test_bad_toml_has_file_location(self):
        self.put(".codex/config.toml", "model = [")
        self.fails(".codex/config.toml", validator.SYNTAX)

    def test_missing_file(self):
        (self.root / ".codex/config.toml").unlink()
        self.fails(".codex/config.toml", validator.SYNTAX)

    def test_old_daily_model(self):
        self.change(".codex/config.toml", 'model = "gpt-5.6-terra"', 'model = "gpt-6-astra"')
        self.fails("V2 requires", validator.POLICY)

    def test_old_daily_effort(self):
        self.change(".codex/config.toml", 'model_reasoning_effort = "medium"', 'model_reasoning_effort = "high"')
        self.fails("model_reasoning_effort", validator.POLICY)

    def test_size_measures_raw_bytes_with_crlf(self):
        p = self.root / "AGENTS.md"
        p.write_bytes("# V2\r\n规则\r\n".encode("utf-8"))
        report = self.check()
        self.assertIn(f"AGENTS.md: {p.stat().st_size} bytes", "\n".join(report["warnings"]))

    def test_old_concurrency(self):
        self.change(".codex/config.toml", "max_concurrent_threads_per_session = 1", "max_concurrent_threads_per_session = 3")
        self.fails("max_concurrent_threads_per_session", validator.POLICY)

    def test_missing_plan_effort(self):
        self.change(".codex/config.toml", 'plan_mode_reasoning_effort = "medium"\n', "")
        self.fails("missing plan_mode_reasoning_effort", validator.SYNTAX)

    def test_wrong_types_including_boolean_as_integer(self):
        for wrong in ('"1"', "true", "1.0"):
            with self.subTest(wrong=wrong):
                p = self.root / ".codex/config.toml"
                before = p.read_text(encoding="utf-8")
                self.put(".codex/config.toml", before.replace("max_concurrent_threads_per_session = 1", "max_concurrent_threads_per_session = " + wrong))
                self.fails("invalid type", validator.SYNTAX)
                p.write_text(before, encoding="utf-8")

    def test_agents_must_be_table(self):
        self.put(".codex/config.toml", 'agents = "invalid"')
        self.fails("expected a TOML table", validator.SYNTAX)

    def test_specialists_cannot_default_xhigh(self):
        for name in ("rrn_core", "rrn_architect"):
            with self.subTest(role=name):
                path = f".codex/agents/{name}.toml"
                self.change(path, 'model_reasoning_effort = "high"', 'model_reasoning_effort = "xhigh"')
                self.fails(name, validator.POLICY)

    def test_required_role_fields(self):
        path = ".codex/agents/rrn_core.toml"
        before = (self.root / path).read_text(encoding="utf-8")
        for key in ("name", "description", "developer_instructions"):
            with self.subTest(key=key):
                self.put(path, "\n".join(line for line in before.splitlines() if not line.startswith(key + " =")))
                self.fails(key, validator.SYNTAX)
        self.put(path, before.replace('description = "A bounded role"', 'description = 7'))
        self.fails("description", validator.SYNTAX)

    def test_name_and_filename_must_match(self):
        self.change(".codex/agents/rrn_core.toml", 'name = "rrn_core"', 'name = "some_core"')
        self.fails("canonical RR filename", validator.SYNTAX)

    def test_duplicate_role_detected_even_in_other_filename(self):
        self.put(".codex/agents/copy.toml", (self.root / ".codex/agents/rrn_core.toml").read_text(encoding="utf-8"))
        self.fails("duplicate role name", validator.SYNTAX)

    def test_missing_role(self):
        (self.root / ".codex/agents/rrn_easy.toml").unlink()
        self.fails("missing ['rrn_easy']", validator.SYNTAX)

    def test_no_delegation_declaration_required(self):
        self.change(".codex/agents/rrn_core.toml", "[agents]\nenabled = false", "")
        self.fails("missing enabled", validator.SYNTAX)

    def test_child_delegation_cannot_be_enabled(self):
        self.change(".codex/agents/rrn_core.toml", "enabled = false", "enabled = true")
        self.fails("V2 requires False", validator.POLICY)

    def test_no_delegation_instruction_required(self):
        self.change(".codex/agents/rrn_core.toml", "不要继续派生子代理。", "Perform assigned work.")
        self.fails("no-child-delegation", validator.POLICY)

    def test_readonly_boundaries_required(self):
        for name in ("rrn_reviewer", "rrn_scout", "rrn_architect"):
            with self.subTest(role=name):
                self.change(f".codex/agents/{name}.toml", 'sandbox_mode = "read-only"\n', "")
                self.fails(name, validator.POLICY)

    def test_write_roles_keep_permission_inheritance(self):
        path = ".codex/agents/rrn_core.toml"
        self.put(path, 'sandbox_mode = "danger-full-access"\n' + (self.root / path).read_text(encoding="utf-8"))
        self.fails("inherit existing permissions", validator.POLICY)

    def test_broken_skill_reference(self):
        self.change(validator.SKILL, "references/task-routing.md", "references/missing.md")
        self.fails("broken reference: references/missing.md", validator.SYNTAX)

    def test_skill_reference_cannot_escape_repo(self):
        self.change(validator.SKILL, "references/task-routing.md", "references/../../../../../outside.md")
        self.fails("escapes repository", validator.SYNTAX)

    def test_invalid_skill_frontmatter(self):
        self.put(validator.SKILL, "# missing frontmatter")
        self.fails("frontmatter", validator.SYNTAX)

    def test_missing_skill_description(self):
        self.change(validator.SKILL, "description: Nontrivial routing only.", "description: ")
        self.fails("description missing", validator.SYNTAX)

    def test_broken_doc_link(self):
        self.put("docs/agent-routing/README.md", "[missing](no-such-file.md)")
        self.fails("broken reference", validator.SYNTAX)

    def test_old_active_policy_detected(self):
        self.put("AGENTS.md", "## Quality-First Codex Collaboration (Plan A)\nAstra/high leads")
        self.fails("superseded active default", validator.POLICY)

    def test_historical_audit_mentions_are_allowed(self):
        self.put("docs/agent-routing/validation.md", "Historical baseline: Astra/high; concurrency 3; core xhigh.\n")
        self.assertFalse(any(self.check()["errors"].values()))

    def test_canonical_memory_must_be_updated(self):
        self.put("PROJECT_MEMORY.md", "- Repository-owned Codex development defaults use quality-first Plan A.")
        self.fails("canonical Codex default", validator.POLICY)

    def test_unrelated_config_and_worktree_preserved(self):
        path = ".codex/config.toml"
        self.put(path, 'model_verbosity = "low"\n' + (self.root / path).read_text(encoding="utf-8"))
        self.put("existing-work.txt", "user work\n")
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        report = self.check()
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(any(report["errors"].values()))
        self.assertIn("not checked against official schema", "\n".join(report["warnings"]))

    def test_missing_tomllib_reports_existing_environment(self):
        with patch.object(validator, "tomllib", None):
            report = validator.validate(self.root)
        self.assertIn("Python 3.11+", "\n".join(report["errors"][validator.SYNTAX]))

    def test_git_not_installed_is_failure(self):
        with patch.object(validator.subprocess, "run", side_effect=FileNotFoundError("git unavailable")):
            report = validator.validate(self.root)
        self.assertIn("git unavailable", "\n".join(report["errors"][validator.POLICY]))

    def test_git_exit_error_is_not_ignored_success(self):
        with patch.object(validator.subprocess, "run", return_value=subprocess.CompletedProcess([], 128, "", "not a repository")):
            report = validator.validate(self.root)
        self.assertIn("Git check failed (128)", "\n".join(report["errors"][validator.POLICY]))

    def init_git(self):
        if not shutil.which("git"):
            self.skipTest("Git integration requires an existing git executable")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        subprocess.run(["git", "config", "core.excludesFile", ""], cwd=self.root, check=True, capture_output=True)

    def test_real_git_ignore_boundaries(self):
        self.init_git()
        self.assertFalse(any(validator.validate(self.root)["errors"].values()))
        with (self.root / ".gitignore").open("a") as f:
            f.write("docs/agent-routing/\n")
        report = validator.validate(self.root)
        self.assertIn("shared file is Git-ignored", "\n".join(report["errors"][validator.POLICY]))

    def test_real_local_log_exposure(self):
        self.init_git()
        self.change(".gitignore", ".tmp/\n", "")
        report = validator.validate(self.root)
        self.assertIn("local state is not Git-ignored", "\n".join(report["errors"][validator.POLICY]))

    def test_optimized_cli_still_rejects_bad_config(self):
        self.init_git()
        self.put(".codex/config.toml", "invalid [")
        result = subprocess.run([sys.executable, "-O", str(self.root / "scripts/validate-codex-config.py")], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("STATIC_SYNTAX: FAIL", result.stdout)
        self.assertIn("RUNTIME_UNVERIFIED", result.stdout)


if __name__ == "__main__":
    unittest.main()
