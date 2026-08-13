from __future__ import annotations

from app.services.ai.knowledge.contracts import (
    KnowledgeCitation,
    KnowledgeDocument,
    KnowledgeSection,
)


def build_knowledge_citation(
    document: KnowledgeDocument,
    section: KnowledgeSection,
) -> KnowledgeCitation:
    entry = document.manifest
    return KnowledgeCitation(
        knowledge_id=entry.knowledge_id,
        version=entry.version,
        section_id=section.section_id,
        source_path=entry.source_path,
        heading=section.heading,
        reviewed_at=entry.reviewed_at,
        content_hash=section.content_hash,
    )


def formal_tool_wins(
    *,
    knowledge_text: str | None,
    formal_tool_text: str | None,
) -> str | None:
    """Static knowledge never overrides current authorized domain Tool facts."""

    if formal_tool_text is not None:
        return formal_tool_text
    return knowledge_text
