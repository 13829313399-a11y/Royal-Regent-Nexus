from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services.ai.evals.contracts import (
    AIEvalCase,
    AIEvalObservation,
    AIEvalToolObservation,
)
from app.services.ai.evals.runner import (
    EvalDatasetError,
    EvalDatasetRegistry,
    run_eval_suite,
)
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.tool_registry import build_default_tool_registry

DATASET_ROOT = Path(__file__).resolve().parent / "evals" / "datasets"


def _skill_registry() -> SkillRegistry:
    return SkillRegistry(
        build_default_tool_registry(
            semantic_gateway_enabled=True,
            knowledge_hub_enabled=True,
            artifact_workflows_enabled=True,
            vision_tool_comparison_enabled=True,
        )
    )


def _matching_observation(case: AIEvalCase) -> AIEvalObservation:
    expected = case.expected
    answer = "；".join(expected.required_answer_terms) or "已按受控边界完成检查"
    return AIEvalObservation(
        selected_skill_id=expected.skill_id,
        answer_text=answer,
        tool_calls=tuple(
            AIEvalToolObservation(
                name=tool.name,
                arguments=tool.required_arguments,
            )
            for tool in expected.tools
        ),
        evidence_levels=expected.evidence_levels,
        error_code=expected.error_code,
        grounded_claims_with_evidence=expected.grounded_claim_count,
        correct_citations=expected.citation_count,
        preview_state=expected.preview_state,
    )


def test_every_current_or_pilot_skill_has_repeatable_offline_eval() -> None:
    registry = _skill_registry()
    datasets = EvalDatasetRegistry(DATASET_ROOT)
    categories: set[str] = set()

    for skill in registry.skills:
        assert skill.manifest.status in {"current", "pilot"}
        assert skill.manifest.eval_suite_ref
        dataset, dataset_hash = datasets.load(skill.manifest.eval_suite_ref)
        assert dataset.mode == "OFFLINE_FAKE"
        categories.update(case.category for case in dataset.cases)
        first = run_eval_suite(
            dataset,
            dataset_hash=dataset_hash,
            skill=skill,
            evaluator=_matching_observation,
        )
        second = run_eval_suite(
            dataset,
            dataset_hash=dataset_hash,
            skill=skill,
            evaluator=_matching_observation,
        )

        assert first == second
        assert first.passed is True
        assert first.provider == "fake"
        assert first.model == "offline-fixture"
        assert first.skill_hash == skill.content_hash
        assert first.prompt_hash == skill.prompt_hash
        assert first.metrics.unauthorized_action_rate == 0
        assert first.metrics.cross_factory_leakage_rate == 0
        assert first.metrics.preview_executed_mislabel_rate == 0
        serialized = json.dumps(first.model_dump(mode="json"), ensure_ascii=False)
        assert '"user_text"' not in serialized
        assert '"answer_text"' not in serialized
        assert '"arguments"' not in serialized
        assert first.raw_prompt_recorded is False
        assert first.raw_tool_result_recorded is False
        assert first.chain_of_thought_recorded is False

    assert categories == {
        "ACTION",
        "BUSINESS_GROUNDING",
        "CHINESE_LANGUAGE",
        "FILE",
        "RESILIENCE",
        "SCHEDULING",
        "SECURITY",
        "VISION",
    }


def test_eval_fails_for_extra_tool_wrong_factory_and_security_flags() -> None:
    registry = _skill_registry()
    datasets = EvalDatasetRegistry(DATASET_ROOT)
    skill = registry.resolve("business.current_page_query")
    dataset, dataset_hash = datasets.load(skill.manifest.eval_suite_ref or "")

    def unsafe_observation(case: AIEvalCase) -> AIEvalObservation:
        matching = _matching_observation(case)
        return matching.model_copy(
            update={
                "tool_calls": (
                    *matching.tool_calls,
                    AIEvalToolObservation(
                        name="identity.get_current_context",
                        arguments={"factory_id": "other-factory"},
                    ),
                ),
                "unauthorized_action": True,
                "cross_factory_leakage": True,
            }
        )

    report = run_eval_suite(
        dataset,
        dataset_hash=dataset_hash,
        skill=skill,
        evaluator=unsafe_observation,
    )

    assert report.passed is False
    assert report.metrics.tool_selection_precision is not None
    assert report.metrics.tool_selection_precision < 1
    assert report.metrics.unauthorized_action_rate > 0
    assert report.metrics.cross_factory_leakage_rate > 0
    assert "TOOL_SELECTION_MISMATCH" in report.results[0].reason_codes


def test_live_provider_eval_is_excluded_from_ordinary_ci() -> None:
    registry = _skill_registry()
    datasets = EvalDatasetRegistry(DATASET_ROOT)
    skill = registry.resolve("system.module_tutor")
    dataset, dataset_hash = datasets.load(skill.manifest.eval_suite_ref or "")
    live_dataset = dataset.model_copy(update={"mode": "LIVE_PROVIDER"})

    with pytest.raises(EvalDatasetError, match="excluded from ordinary CI"):
        run_eval_suite(
            live_dataset,
            dataset_hash=dataset_hash,
            skill=skill,
            evaluator=_matching_observation,
        )


def test_eval_rejects_stale_skill_or_prompt_version() -> None:
    registry = _skill_registry()
    datasets = EvalDatasetRegistry(DATASET_ROOT)
    skill = registry.resolve("system.module_tutor")
    dataset, dataset_hash = datasets.load(skill.manifest.eval_suite_ref or "")

    with pytest.raises(EvalDatasetError, match="Skill version is stale"):
        run_eval_suite(
            dataset.model_copy(update={"skill_version": "0.0.1"}),
            dataset_hash=dataset_hash,
            skill=skill,
            evaluator=_matching_observation,
        )
    with pytest.raises(EvalDatasetError, match="Prompt version is stale"):
        run_eval_suite(
            dataset.model_copy(update={"prompt_version": "0.0.1"}),
            dataset_hash=dataset_hash,
            skill=skill,
            evaluator=_matching_observation,
        )
