import asyncio
import json

from app.core.config import Settings
from app.schemas.ai import AIPageContextInput, AIServerPageContext
from app.services.ai.context_builder import build_server_page_context
from app.services.ai.knowledge.citations import build_knowledge_citation
from app.services.ai.knowledge.registry import KnowledgeRegistry
from app.services.ai.providers import ProviderToolCall
from app.services.ai.tool_executor import ToolExecutionContext, ToolExecutor
from app.services.ai.tool_registry import build_default_tool_registry
from app.services.auth import AuthContext


def _context() -> ToolExecutionContext:
    user = AuthContext(
        id="knowledge-user",
        username="knowledge-user",
        display_name="Knowledge User",
        roles=("Pilot",),
        role_codes=("planner",),
        permissions=frozenset(),
        factory_scopes=("huaxing",),
        department_scopes=("production",),
        active_permission_codes=frozenset(),
    )
    return ToolExecutionContext(
        None,
        user,
        "request-knowledge",
        AIServerPageContext(
            verified_route_name="injection-scheduling-v2",
            verified_path="/modules/production/injection-scheduling",
            verified_factory_id="huaxing",
            verified_module_id="injection-scheduling",
            knowledge_id="injection-scheduling",
            allowed_tool_groups=("identity", "module_knowledge", "injection_scheduling"),
        ),
    )


def test_citation_binds_document_version_section_and_content_hash() -> None:
    document = KnowledgeRegistry().load("injection-scheduling")
    section = document.sections[0]
    citation = build_knowledge_citation(document, section)

    assert citation.knowledge_id == document.manifest.knowledge_id
    assert citation.version == document.manifest.version
    assert citation.section_id == section.section_id
    assert citation.source_path == document.manifest.source_path
    assert citation.content_hash == section.content_hash


def test_workbench_context_exposes_knowledge_only_behind_the_feature_flag() -> None:
    user = _context().user
    request = AIPageContextInput(
        route_name="ai-workbench",
        path="/workbench/ai",
        factory_id=None,
        module_id="ai-workbench",
    )

    disabled = build_server_page_context(request, user)
    enabled = build_server_page_context(request, user, knowledge_hub_enabled=True)

    assert disabled is not None
    assert disabled.knowledge_id == "ai-usage"
    assert disabled.allowed_tool_groups == ("identity",)
    assert enabled is not None
    assert enabled.verified_factory_id is None
    assert enabled.allowed_tool_groups == ("identity", "module_knowledge")


def test_knowledge_tool_returns_citations_and_versioned_evidence() -> None:
    registry = build_default_tool_registry(knowledge_hub_enabled=True)
    call = ProviderToolCall(
        call_id="call-knowledge",
        name="knowledge.search_module",
        arguments_json=json.dumps({"query": "DRAFT PUBLISHED", "max_results": 2}),
    )
    outcome = asyncio.run(
        ToolExecutor(
            registry,
            Settings(
                _env_file=None,
                ai_nif_runtime_enabled=True,
                ai_evidence_v1_enabled=True,
            ),
        ).execute(call, _context())
    )
    payload = json.loads(outcome.provider_output_json)

    assert outcome.ok is True
    assert payload["data"]["schema_version"] == "knowledge-search-v1"
    assert payload["data"]["hits"]
    assert payload["data"]["hits"][0]["citation"]["section_id"]
    assert payload["evidence"][0]["source_level"] == "VERSIONED_MODULE_KNOWLEDGE"
    assert payload["evidence"][0]["source_name"] == "knowledge.search_module"


def test_knowledge_tool_reports_missing_evidence_without_fabricating_hits() -> None:
    registry = build_default_tool_registry(knowledge_hub_enabled=True)
    outcome = asyncio.run(
        ToolExecutor(registry, Settings(_env_file=None)).execute(
            ProviderToolCall(
                call_id="call-knowledge-missing",
                name="knowledge.search_module",
                arguments_json='{"query":"zzzz-no-evidence-9999"}',
            ),
            _context(),
        )
    )
    payload = json.loads(outcome.provider_output_json)

    assert outcome.ok is True
    assert payload["data"]["evidence_missing"] is True
    assert payload["data"]["hits"] == []
