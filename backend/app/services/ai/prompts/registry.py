from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from app.services.ai.skills.contracts import SkillRegistryError

_PROMPT_ROOT = Path(__file__).resolve().parent
_SKILL_ID = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*['\"]?[^\s'\"]{8,}"
    ),
)


@dataclass(frozen=True, slots=True)
class PromptFragment:
    fragment_id: str
    version: str
    content: str
    content_hash: str


def _normalized(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PromptRegistry:
    """Read-only registry for reviewed repository Prompt fragments."""

    def __init__(self, *, prompt_root: Path = _PROMPT_ROOT) -> None:
        self._prompt_root = prompt_root.resolve()

    def load_core(self) -> PromptFragment:
        return self._load("core.policy", "1.2.0", "core_policy.md")

    def load_skill(self, skill_id: str, version: str) -> PromptFragment:
        if _SKILL_ID.fullmatch(skill_id) is None:
            raise SkillRegistryError("invalid Skill Prompt id")
        return self._load(skill_id, version, f"skills/{skill_id}.md")

    def _load(self, fragment_id: str, version: str, relative_path: str) -> PromptFragment:
        candidate = (self._prompt_root / relative_path).resolve()
        if not candidate.is_relative_to(self._prompt_root):
            raise SkillRegistryError("Prompt path escapes registry")
        try:
            content = _normalized(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise SkillRegistryError("registered Prompt fragment is unavailable") from exc
        if not content:
            raise SkillRegistryError("registered Prompt fragment is empty")
        if any(pattern.search(content) for pattern in _SECRET_PATTERNS):
            raise SkillRegistryError("Prompt fragment contains a secret-like value")
        return PromptFragment(
            fragment_id=fragment_id,
            version=version,
            content=content,
            content_hash=_digest(content),
        )
