from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_METADATA_BLOCK = re.compile(
    r"\A<!-- ai-module-knowledge-metadata\s*\n"
    r"(?P<metadata>\{.*\})\s*\n-->\s*\n(?P<body>.+)\Z",
    re.DOTALL,
)
_DEFAULT_KNOWLEDGE_FILES = MappingProxyType(
    {
        "injection-scheduling": "docs/ai/modules/injection-scheduling.md",
    }
)
_ROUTE_KNOWLEDGE_IDS = MappingProxyType(
    {
        "injection-scheduling-v2": "injection-scheduling",
    }
)
_EXPECTED_ROUTES = MappingProxyType(
    {
        "injection-scheduling": ("injection-scheduling-v2",),
    }
)


class ModuleKnowledgeError(ValueError):
    """A versioned knowledge document failed closed validation."""


class UnknownModuleKnowledgeError(ModuleKnowledgeError):
    pass


class ModuleKnowledgeMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    knowledge_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9-]+$",
    )
    knowledge_version: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$",
    )
    last_reviewed_at: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    reviewed_against_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    route_names: tuple[str, ...] = Field(min_length=1, max_length=8)
    module_name: str = Field(min_length=1, max_length=128)
    business_purpose: str = Field(min_length=1, max_length=1_024)
    authoritative_data_status: str = Field(min_length=1, max_length=1_024)
    required_permissions: tuple[str, ...] = Field(min_length=1, max_length=32)
    normal_workflow: tuple[str, ...] = Field(min_length=1, max_length=32)
    status_labels: dict[str, str] = Field(min_length=1, max_length=64)
    common_errors: tuple[str, ...] = Field(min_length=1, max_length=32)
    prohibited_claims: tuple[str, ...] = Field(min_length=1, max_length=32)
    source_files: tuple[str, ...] = Field(min_length=1, max_length=64)

    @field_validator(
        "route_names",
        "required_permissions",
        "normal_workflow",
        "common_errors",
        "prohibited_claims",
        "source_files",
    )
    @classmethod
    def validate_unique_nonempty_items(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not value or value != value.strip() for value in values):
            raise ValueError("knowledge list values must be non-empty and normalized")
        if len(values) != len(set(values)):
            raise ValueError("knowledge list values must be unique")
        return values

    @field_validator("status_labels")
    @classmethod
    def validate_status_labels(cls, values: dict[str, str]) -> dict[str, str]:
        if any(
            not key
            or key != key.strip()
            or not value
            or value != value.strip()
            for key, value in values.items()
        ):
            raise ValueError("status labels must be non-empty and normalized")
        return values


class ModuleKnowledgeDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: ModuleKnowledgeMetadata
    body_markdown: str = Field(min_length=1, max_length=32_000)


class ModuleKnowledgeRegistry:
    """Loads only server-registered repository files, never request-derived paths."""

    def __init__(
        self,
        *,
        repository_root: Path = _REPOSITORY_ROOT,
        knowledge_files: Mapping[str, str] = _DEFAULT_KNOWLEDGE_FILES,
    ) -> None:
        self._repository_root = repository_root.resolve()
        self._knowledge_files = MappingProxyType(dict(knowledge_files))
        for knowledge_id, relative_path in self._knowledge_files.items():
            if not knowledge_id or knowledge_id != knowledge_id.strip():
                raise ModuleKnowledgeError("invalid registered knowledge id")
            _validate_relative_path(relative_path)

    def load_for_route(self, route_name: str) -> ModuleKnowledgeDocument:
        knowledge_id = _ROUTE_KNOWLEDGE_IDS.get(route_name)
        if knowledge_id is None:
            raise UnknownModuleKnowledgeError("route has no registered module knowledge")
        return self.load(knowledge_id)

    def load(self, knowledge_id: str) -> ModuleKnowledgeDocument:
        relative_path = self._knowledge_files.get(knowledge_id)
        if relative_path is None:
            raise UnknownModuleKnowledgeError("module knowledge is not registered")

        knowledge_path = self._resolve_repository_path(relative_path)
        try:
            raw_document = knowledge_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ModuleKnowledgeError("module knowledge file is unavailable") from exc

        match = _METADATA_BLOCK.fullmatch(raw_document)
        if match is None:
            raise ModuleKnowledgeError("module knowledge metadata block is missing")
        try:
            raw_metadata = json.loads(match.group("metadata"))
            metadata = ModuleKnowledgeMetadata.model_validate(raw_metadata)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ModuleKnowledgeError("module knowledge metadata is invalid") from exc

        if metadata.knowledge_id != knowledge_id:
            raise ModuleKnowledgeError("module knowledge id does not match registry")
        if metadata.route_names != _EXPECTED_ROUTES.get(knowledge_id):
            raise ModuleKnowledgeError("module knowledge route allowlist does not match")
        for source_file in metadata.source_files:
            if PurePosixPath(source_file).name in {"PROJECT_MEMORY.md", "AGENTS.md"}:
                raise ModuleKnowledgeError("development knowledge source is forbidden")
            source_path = self._resolve_repository_path(source_file)
            if not source_path.is_file():
                raise ModuleKnowledgeError("module knowledge source file is unavailable")

        body_markdown = match.group("body").strip()
        try:
            return ModuleKnowledgeDocument(
                metadata=metadata,
                body_markdown=body_markdown,
            )
        except ValidationError as exc:
            raise ModuleKnowledgeError("module knowledge body is invalid") from exc

    def _resolve_repository_path(self, relative_path: str) -> Path:
        _validate_relative_path(relative_path)
        candidate = (self._repository_root / relative_path).resolve()
        if not candidate.is_relative_to(self._repository_root):
            raise ModuleKnowledgeError("module knowledge path escapes repository")
        return candidate


def _validate_relative_path(value: str) -> None:
    if not value or value != value.strip() or "\\" in value:
        raise ModuleKnowledgeError("module knowledge paths must be normalized")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise ModuleKnowledgeError("module knowledge paths must be repository-relative")


module_knowledge_registry = ModuleKnowledgeRegistry()
