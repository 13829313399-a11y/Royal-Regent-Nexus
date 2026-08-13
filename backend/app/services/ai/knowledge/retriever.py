from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Protocol

from app.services.ai.knowledge.citations import build_knowledge_citation
from app.services.ai.knowledge.contracts import (
    KnowledgeClassification,
    KnowledgeDocument,
    KnowledgeHit,
    KnowledgeLifecycle,
    KnowledgeSearchResult,
    KnowledgeSection,
)
from app.services.ai.knowledge.registry import KnowledgeRegistry

_TOKEN = re.compile(r"[a-z0-9][a-z0-9._:-]*|[\u3400-\u9fff]+")


class KnowledgeRetrievalError(ValueError):
    pass


class KnowledgeDocumentSource(Protocol):
    """Adapter seam for local Git today and measured PostgreSQL FTS later."""

    def load(self, knowledge_id: str) -> KnowledgeDocument: ...


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def _terms(value: str) -> tuple[str, ...]:
    terms: list[str] = []
    for match in _TOKEN.finditer(_normalize(value)):
        token = match.group(0)
        terms.append(token)
        if any("\u3400" <= character <= "\u9fff" for character in token):
            terms.extend(token[index : index + 2] for index in range(len(token) - 1))
    return tuple(dict.fromkeys(item for item in terms if item))


class KnowledgeRetriever:
    """Bounded exact/keyword retrieval over the reviewed local Git corpus."""

    def __init__(self, registry: KnowledgeDocumentSource | None = None) -> None:
        self._registry = registry or KnowledgeRegistry()

    def search(
        self,
        query: str,
        *,
        knowledge_ids: tuple[str, ...],
        user_role_codes: tuple[str, ...],
        factory_id: str | None,
        pilot: bool,
        on_date: date,
        max_hits: int = 3,
        include_development: bool = False,
    ) -> KnowledgeSearchResult:
        normalized_query = _normalize(query)
        if len(normalized_query) > 200:
            raise KnowledgeRetrievalError("Knowledge query is too long")
        if not 1 <= max_hits <= 5:
            raise KnowledgeRetrievalError("Knowledge result limit is invalid")
        documents = tuple(
            document
            for knowledge_id in tuple(dict.fromkeys(knowledge_ids))
            if self._is_accessible(
                document := self._registry.load(knowledge_id),
                user_role_codes=user_role_codes,
                factory_id=factory_id,
                pilot=pilot,
                on_date=on_date,
                include_development=include_development,
            )
        )
        ranked: list[tuple[int, KnowledgeDocument, KnowledgeSection]] = []
        query_terms = _terms(normalized_query)
        for document in documents:
            keywords = tuple(_normalize(item) for item in document.manifest.keywords)
            for section in document.sections:
                score = self._score(
                    normalized_query,
                    query_terms,
                    section.normalized_text,
                    keywords,
                )
                if score > 0:
                    ranked.append((score, document, section))
        ranked.sort(
            key=lambda item: (
                -item[0],
                item[1].manifest.knowledge_id,
                item[2].section_id,
            )
        )
        selected = ranked[:max_hits]
        hits = tuple(
            KnowledgeHit(
                score=score,
                text_markdown=section.body_markdown,
                citation=build_knowledge_citation(document, section),
                deep_links=document.manifest.deep_links,
            )
            for score, document, section in selected
        )
        missing = not hits
        return KnowledgeSearchResult(
            query=query.strip(),
            evidence_missing=missing,
            message=(
                "没有找到可用于回答当前问题的有效模块知识，请在系统中核对或联系模块负责人。"
                if missing
                else "已找到经过 Owner 审核且仍在有效期内的模块知识；实时业务事实仍以正式 Tool 为准。"
            ),
            hits=hits,
            truncated=len(ranked) > len(selected),
        )

    @staticmethod
    def _is_accessible(
        document: KnowledgeDocument,
        *,
        user_role_codes: tuple[str, ...],
        factory_id: str | None,
        pilot: bool,
        on_date: date,
        include_development: bool,
    ) -> bool:
        entry = document.manifest
        if (
            entry.classification is KnowledgeClassification.K2_DEVELOPMENT
            and not include_development
        ):
            return False
        status = entry.effective_status(on_date)
        if status is KnowledgeLifecycle.PILOT_READY and not pilot:
            return False
        if status not in {KnowledgeLifecycle.PILOT_READY, KnowledgeLifecycle.PUBLISHED}:
            return False
        if "*" not in entry.role_codes and not set(entry.role_codes).intersection(
            user_role_codes
        ):
            return False
        return "*" in entry.factory_ids or (
            factory_id is not None and factory_id in entry.factory_ids
        )

    @staticmethod
    def _score(
        query: str,
        query_terms: tuple[str, ...],
        section_text: str,
        keywords: tuple[str, ...],
    ) -> int:
        if not query:
            return 10
        score = 0
        if query in section_text:
            score += 500
        for keyword in keywords:
            if keyword and keyword in query and keyword in section_text:
                score += 80
        for term in query_terms:
            if term in section_text:
                score += min(30, len(term) * 5)
        return min(score, 1_000)
