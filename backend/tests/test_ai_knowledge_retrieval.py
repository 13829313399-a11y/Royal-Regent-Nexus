from datetime import date

import pytest
from app.services.ai.knowledge.citations import formal_tool_wins
from app.services.ai.knowledge.contracts import (
    KnowledgeClassification,
    KnowledgeDocument,
)
from app.services.ai.knowledge.registry import KnowledgeRegistry
from app.services.ai.knowledge.retriever import KnowledgeRetriever


class _OneDocumentRegistry:
    def __init__(self, document: KnowledgeDocument) -> None:
        self.document = document

    def load(self, knowledge_id: str) -> KnowledgeDocument:
        assert knowledge_id == self.document.manifest.knowledge_id
        return self.document


def _search(
    retriever: KnowledgeRetriever,
    query: str,
    *,
    roles: tuple[str, ...] = ("planner",),
    factory_id: str | None = "huaxing",
    include_development: bool = False,
):
    return retriever.search(
        query,
        knowledge_ids=("injection-scheduling",),
        user_role_codes=roles,
        factory_id=factory_id,
        pilot=True,
        on_date=date(2026, 8, 12),
        include_development=include_development,
    )


def test_exact_and_chinese_keyword_search_return_bounded_exact_citations() -> None:
    result = _search(KnowledgeRetriever(), "DRAFT 和 PUBLISHED 有什么区别")

    assert result.evidence_missing is False
    assert 1 <= len(result.hits) <= 3
    assert all(hit.citation.knowledge_id == "injection-scheduling" for hit in result.hits)
    assert all(hit.citation.version == "1.1.0" for hit in result.hits)
    assert all(hit.citation.section_id for hit in result.hits)
    assert all(hit.citation.content_hash.startswith("sha256:") for hit in result.hits)
    assert result.conflict_policy == "FORMAL_TOOL_WINS"


@pytest.mark.parametrize(
    ("knowledge_id", "query"),
    (
        ("ai-usage", "这个页面怎么用"),
        ("internal-quote", "为什么我看不到发布按钮"),
        ("molding-sample", "样办生产任务怎么处理"),
        ("carton-procurement", "纸箱采购正常流程"),
        ("raw-material", "主数据和厂区库存有什么区别"),
        ("customer-order", "客户订单中心目前能做什么"),
        ("injection-scheduling", "DRAFT 和 PUBLISHED 有什么区别"),
        ("injection-scheduling", "401 403 409 错误码是什么意思"),
    ),
)
def test_first_wave_product_eval_questions_have_reviewed_cited_evidence(
    knowledge_id: str,
    query: str,
) -> None:
    result = KnowledgeRetriever().search(
        query,
        knowledge_ids=(knowledge_id,),
        user_role_codes=("pilot",),
        factory_id="huaxing",
        pilot=True,
        on_date=date(2026, 8, 12),
    )

    assert result.evidence_missing is False
    assert result.hits
    assert all(hit.citation.knowledge_id == knowledge_id for hit in result.hits)
    assert all(hit.citation.section_id for hit in result.hits)


def test_missing_evidence_is_explicit_and_never_model_filled() -> None:
    result = _search(KnowledgeRetriever(), "zzzz-no-reviewed-evidence-9999")

    assert result.evidence_missing is True
    assert result.hits == ()
    assert "没有找到" in result.message


def test_role_factory_expiry_and_k2_filters_fail_closed() -> None:
    original = KnowledgeRegistry().load("injection-scheduling")
    restricted = original.model_copy(
        update={
            "manifest": original.manifest.model_copy(
                update={
                    "factory_ids": ("huakang-b",),
                    "role_codes": ("module-owner",),
                }
            )
        }
    )
    retriever = KnowledgeRetriever(_OneDocumentRegistry(restricted))

    assert _search(retriever, "排产", roles=("planner",), factory_id="huaxing").evidence_missing
    allowed = _search(
        retriever,
        "排产",
        roles=("module-owner",),
        factory_id="huakang-b",
    )
    assert not allowed.evidence_missing

    development = restricted.model_copy(
        update={
            "manifest": restricted.manifest.model_copy(
                update={
                    "classification": KnowledgeClassification.K2_DEVELOPMENT,
                }
            )
        }
    )
    development_retriever = KnowledgeRetriever(_OneDocumentRegistry(development))
    assert _search(
        development_retriever,
        "排产",
        roles=("module-owner",),
        factory_id="huakang-b",
    ).evidence_missing
    assert not _search(
        development_retriever,
        "排产",
        roles=("module-owner",),
        factory_id="huakang-b",
        include_development=True,
    ).evidence_missing

    expired = restricted.model_copy(
        update={
            "manifest": restricted.manifest.model_copy(
                update={"expires_at": date(2026, 8, 11)}
            )
        }
    )
    assert _search(
        KnowledgeRetriever(_OneDocumentRegistry(expired)),
        "排产",
        roles=("module-owner",),
        factory_id="huakang-b",
    ).evidence_missing


def test_knowledge_is_guidance_and_formal_tool_result_wins() -> None:
    assert formal_tool_wins(
        knowledge_text="旧流程说明",
        formal_tool_text="当前正式业务状态",
    ) == "当前正式业务状态"
    assert formal_tool_wins(
        knowledge_text="现有流程说明",
        formal_tool_text=None,
    ) == "现有流程说明"

    customer = KnowledgeRetriever().search(
        "官方订单总数和权威总台账",
        knowledge_ids=("customer-order",),
        user_role_codes=("sales",),
        factory_id="huaxing",
        pilot=True,
        on_date=date(2026, 8, 12),
    )
    assert customer.hits
    assert any("没有权威订单总台账" in hit.text_markdown for hit in customer.hits)
