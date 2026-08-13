import subprocess
from datetime import date
from pathlib import Path

import pytest
import yaml
from app.services.ai.knowledge.contracts import KnowledgeLifecycle
from app.services.ai.knowledge.registry import KnowledgeRegistry, KnowledgeRegistryError


def _entry(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "knowledge_id": "sample-help",
        "version": "1.0.0",
        "owner": "sample-owner",
        "status": "PILOT_READY",
        "reviewed_at": "2026-08-12",
        "reviewed_by": "sample-reviewer",
        "expires_at": "2027-02-08",
        "classification": "K1_BUSINESS_MODULE",
        "module_id": "sample-module",
        "route_names": ["sample-route"],
        "source_path": "docs/ai/modules/sample-help.md",
        "source_files": ["bound-source.txt"],
        "factory_ids": ["huaxing"],
        "role_codes": ["planner"],
        "keywords": ["sample", "help"],
        "deep_links": [{"label": "Sample", "path": "/modules/molding-sample"}],
    }
    value.update(overrides)
    return value


def _registry(tmp_path: Path, documents: list[dict[str, object]]) -> KnowledgeRegistry:
    source_root = tmp_path / "docs" / "ai" / "modules"
    source_root.mkdir(parents=True)
    (source_root / "sample-help.md").write_text(
        "# Sample help\n\n"
        "<!-- knowledge-section:overview -->\n"
        "## Overview\n\nReviewed process guidance.\n",
        encoding="utf-8",
    )
    (tmp_path / "bound-source.txt").write_text("bound", encoding="utf-8")
    manifest = tmp_path / "docs" / "ai" / "knowledge-manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {"schema_version": "knowledge-manifest-v1", "documents": documents},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return KnowledgeRegistry(repository_root=tmp_path)


def test_repository_manifest_has_seven_owner_reviewed_pilot_documents() -> None:
    registry = KnowledgeRegistry()
    documents = registry.validate_all(
        on_date=date(2026, 8, 12),
        require_current=True,
    )

    assert len(documents) == 7
    assert {item.manifest.knowledge_id for item in documents} == {
        "ai-usage",
        "internal-quote",
        "molding-sample",
        "carton-procurement",
        "raw-material",
        "customer-order",
        "injection-scheduling",
    }
    assert all(
        item.manifest.status is KnowledgeLifecycle.PILOT_READY for item in documents
    )
    assert all(item.sections for item in documents)
    assert registry.knowledge_id_for_route("ai-workbench") == "ai-usage"


def test_repository_knowledge_delivery_files_are_not_gitignored() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    registry = KnowledgeRegistry(repository_root=repository_root)
    delivery_paths = [
        *(item.source_path for item in registry.entries),
        "docs/ai/knowledge-manifest.yaml",
        "docs/ai/knowledge-review-queue/README.md",
    ]

    for relative_path in delivery_paths:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", "--", relative_path],
            cwd=repository_root,
            check=False,
        )
        assert result.returncode == 1, f"Knowledge delivery file is ignored: {relative_path}"


def test_registry_rejects_duplicate_invalid_or_development_sources(
    tmp_path: Path,
) -> None:
    with pytest.raises(KnowledgeRegistryError, match="manifest is invalid"):
        _registry(tmp_path / "duplicate", [_entry(), _entry()])

    with pytest.raises(KnowledgeRegistryError, match="forbidden"):
        _registry(
            tmp_path / "development",
            [_entry(source_files=["PROJECT_MEMORY.md"])],
        )

    with pytest.raises(KnowledgeRegistryError, match="relative"):
        _registry(
            tmp_path / "traversal",
            [_entry(source_path="../outside.md")],
        )

    with pytest.raises(KnowledgeRegistryError, match="manifest is invalid"):
        _registry(tmp_path / "published", [_entry(status="PUBLISHED")])

    evaluated_fields = {
        "eval_dataset_ref": "dataset-v1",
        "eval_runner_ref": "runner-v1",
        "eval_result_ref": "results/eval-v1.json",
        "evaluated_at": "2026-08-12",
        "evaluated_by": "evaluation-reviewer",
    }
    with pytest.raises(KnowledgeRegistryError, match="NIF-17"):
        _registry(
            tmp_path / "premature-published",
            [_entry(status="PUBLISHED", **evaluated_fields)],
        )

    with pytest.raises(KnowledgeRegistryError, match="deep link"):
        _registry(
            tmp_path / "unsafe-link",
            [_entry(deep_links=[{"label": "Admin", "path": "/system/users"}])],
        )


def test_expired_knowledge_fails_current_validation(tmp_path: Path) -> None:
    registry = _registry(
        tmp_path,
        [
            _entry(
                reviewed_at="2026-01-01",
                expires_at="2026-02-01",
            )
        ],
    )

    assert registry.entry("sample-help").effective_status(date(2026, 8, 12)) is (
        KnowledgeLifecycle.EXPIRED
    )
    with pytest.raises(KnowledgeRegistryError, match="expired"):
        registry.validate_all(on_date=date(2026, 8, 12), require_current=True)
