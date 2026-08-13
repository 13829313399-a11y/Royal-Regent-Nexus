from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from pathlib import Path, PurePosixPath

import yaml
from pydantic import ValidationError

from app.core.time import business_now
from app.services.ai.knowledge.contracts import (
    KnowledgeDocument,
    KnowledgeLifecycle,
    KnowledgeManifest,
    KnowledgeManifestEntry,
    KnowledgeSection,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_MANIFEST_PATH = "docs/ai/knowledge-manifest.yaml"
_SOURCE_ROOT = PurePosixPath("docs/ai/modules")
_SECTION_MARKER = re.compile(
    r"^<!-- knowledge-section:(?P<id>[a-z0-9]+(?:-[a-z0-9]+)*) -->\s*$",
    re.MULTILINE,
)
_HEADING = re.compile(r"^#{1,3}\s+(?P<title>[^\n]+)$", re.MULTILINE)
_LEGACY_METADATA = re.compile(
    r"\A<!-- ai-module-knowledge-metadata\s*\n.*?\n-->\s*\n",
    re.DOTALL,
)
_FORBIDDEN_SOURCES = {
    "PROJECT_MEMORY.md",
    "AGENTS.md",
    "backend/.env",
    ".env",
}
_FORBIDDEN_SOURCE_NAMES = {"PROJECT_MEMORY.md", "AGENTS.md"}
_ALLOWED_DEEP_LINKS = {
    "/workbench/ai",
    "/modules/sales-business/internal-quote-desk",
    "/modules/molding-sample",
    "/modules/pmc-warehouse/carton-procurement",
    "/modules/pmc-warehouse/raw-material-management",
    "/modules/sales-business/po-schedule-intake",
    "/modules/production/injection-scheduling",
}


class KnowledgeRegistryError(ValueError):
    """Git Knowledge failed closed validation."""


def _hash(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[`*_>#\[\]()]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _validated_relative_path(value: str) -> PurePosixPath:
    if not value or value != value.strip() or "\\" in value:
        raise KnowledgeRegistryError("Knowledge paths must be normalized")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise KnowledgeRegistryError("Knowledge paths must be repository-relative")
    return path


class KnowledgeRegistry:
    """Loads only reviewed, manifest-bound repository Knowledge."""

    def __init__(
        self,
        *,
        repository_root: Path = _REPOSITORY_ROOT,
        manifest_path: str = _DEFAULT_MANIFEST_PATH,
        allow_evaluated_statuses: bool = False,
    ) -> None:
        self._repository_root = repository_root.resolve()
        self._manifest_path = _validated_relative_path(manifest_path)
        self._allow_evaluated_statuses = allow_evaluated_statuses
        self._manifest = self._load_manifest()
        self._by_id = {item.knowledge_id: item for item in self._manifest.documents}
        self._by_route = {
            route: item.knowledge_id
            for item in self._manifest.documents
            for route in item.route_names
        }

    @property
    def manifest(self) -> KnowledgeManifest:
        return self._manifest

    @property
    def entries(self) -> tuple[KnowledgeManifestEntry, ...]:
        return tuple(sorted(self._manifest.documents, key=lambda item: item.knowledge_id))

    def entry(self, knowledge_id: str) -> KnowledgeManifestEntry:
        entry = self._by_id.get(knowledge_id)
        if entry is None:
            raise KnowledgeRegistryError("Knowledge ID is not registered")
        return entry

    def knowledge_id_for_route(self, route_name: str) -> str:
        knowledge_id = self._by_route.get(route_name)
        if knowledge_id is None:
            raise KnowledgeRegistryError("Route has no registered Knowledge")
        return knowledge_id

    def load_for_route(self, route_name: str) -> KnowledgeDocument:
        return self.load(self.knowledge_id_for_route(route_name))

    def load(self, knowledge_id: str) -> KnowledgeDocument:
        entry = self.entry(knowledge_id)
        source_path = self._resolve(entry.source_path)
        try:
            raw = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise KnowledgeRegistryError("Knowledge document is unavailable") from exc
        body = _LEGACY_METADATA.sub("", raw).strip()
        title_match = _HEADING.search(body)
        if title_match is None:
            raise KnowledgeRegistryError("Knowledge document title is missing")
        sections = self._parse_sections(body)
        return KnowledgeDocument(
            manifest=entry,
            title=title_match.group("title").strip(),
            sections=sections,
            content_hash=_hash(body),
        )

    def validate_all(
        self,
        *,
        on_date: date | None = None,
        require_current: bool = False,
    ) -> tuple[KnowledgeDocument, ...]:
        today = on_date or business_now().date()
        documents: list[KnowledgeDocument] = []
        for entry in self.entries:
            status = entry.effective_status(today)
            if require_current and status in {
                KnowledgeLifecycle.EXPIRED,
                KnowledgeLifecycle.RETIRED,
            }:
                raise KnowledgeRegistryError("Active Knowledge is expired or retired")
            documents.append(self.load(entry.knowledge_id))
        return tuple(documents)

    def _load_manifest(self) -> KnowledgeManifest:
        path = self._resolve(str(self._manifest_path))
        try:
            raw = path.read_text(encoding="utf-8")
            payload = yaml.safe_load(raw)
            manifest = KnowledgeManifest.model_validate(payload)
        except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as exc:
            raise KnowledgeRegistryError("Knowledge manifest is invalid") from exc
        for entry in manifest.documents:
            if (
                not self._allow_evaluated_statuses
                and entry.status
                in {KnowledgeLifecycle.EVAL_PASSED, KnowledgeLifecycle.PUBLISHED}
            ):
                raise KnowledgeRegistryError(
                    "NIF-17 must explicitly unlock evaluated Knowledge statuses"
                )
            self._validate_entry_paths(entry)
        return manifest

    def _validate_entry_paths(self, entry: KnowledgeManifestEntry) -> None:
        source = _validated_relative_path(entry.source_path)
        if source.parent != _SOURCE_ROOT or source.suffix.lower() != ".md":
            raise KnowledgeRegistryError("Knowledge source is outside allowed directory")
        if not self._resolve(entry.source_path).is_file():
            raise KnowledgeRegistryError("Knowledge source document is unavailable")
        for source_file in entry.source_files:
            candidate = _validated_relative_path(source_file)
            if (
                str(candidate) in _FORBIDDEN_SOURCES
                or candidate.name in _FORBIDDEN_SOURCE_NAMES
                or candidate.name.startswith(".env")
            ):
                raise KnowledgeRegistryError("Development or secret source is forbidden")
            if not self._resolve(source_file).is_file():
                raise KnowledgeRegistryError("Knowledge bound source is unavailable")
        link_paths = [link.path for link in entry.deep_links]
        if len(link_paths) != len(set(link_paths)):
            raise KnowledgeRegistryError("Knowledge deep links must be unique")
        if any(path not in _ALLOWED_DEEP_LINKS for path in link_paths):
            raise KnowledgeRegistryError("Knowledge deep link is not allowlisted")

    def _parse_sections(self, body: str) -> tuple[KnowledgeSection, ...]:
        matches = tuple(_SECTION_MARKER.finditer(body))
        if not matches:
            raise KnowledgeRegistryError("Knowledge document has no stable sections")
        sections: list[KnowledgeSection] = []
        for index, marker in enumerate(matches):
            start = marker.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            section_body = body[start:end].strip()
            heading_match = _HEADING.search(section_body)
            if heading_match is None or heading_match.start() != 0:
                raise KnowledgeRegistryError("Knowledge section heading is missing")
            normalized = _normalized_text(section_body)
            if not normalized:
                raise KnowledgeRegistryError("Knowledge section is empty")
            sections.append(
                KnowledgeSection(
                    section_id=marker.group("id"),
                    heading=heading_match.group("title").strip(),
                    body_markdown=section_body,
                    normalized_text=normalized,
                    content_hash=_hash(section_body),
                )
            )
        ids = [section.section_id for section in sections]
        if len(ids) != len(set(ids)):
            raise KnowledgeRegistryError("Knowledge section IDs must be unique")
        return tuple(sections)

    def _resolve(self, relative_path: str) -> Path:
        normalized = _validated_relative_path(relative_path)
        candidate = (self._repository_root / Path(*normalized.parts)).resolve()
        if not candidate.is_relative_to(self._repository_root):
            raise KnowledgeRegistryError("Knowledge path escapes repository")
        return candidate
