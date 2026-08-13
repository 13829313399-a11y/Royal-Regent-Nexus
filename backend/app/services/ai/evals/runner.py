from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from app.services.ai.evals.contracts import (
    AIEvalAggregateMetrics,
    AIEvalCase,
    AIEvalCaseResult,
    AIEvalDataset,
    AIEvalObservation,
    AIEvalReport,
)
from app.services.ai.skills.contracts import RegisteredSkill

RUNNER_VERSION = "1.0.0"
_MAX_DATASET_BYTES = 1024 * 1024


class EvalDatasetError(ValueError):
    pass


class EvalDatasetRegistry:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def load(self, suite_id: str) -> tuple[AIEvalDataset, str]:
        if not suite_id or not suite_id.replace("_", "a").isalnum():
            raise EvalDatasetError("invalid Eval suite id")
        path = (self._root / f"{suite_id}.json").resolve()
        if path.parent != self._root or path.is_symlink():
            raise EvalDatasetError("Eval dataset path is not allowed")
        try:
            payload_bytes = path.read_bytes()
        except OSError as exc:
            raise EvalDatasetError("Eval dataset is unavailable") from exc
        if not payload_bytes or len(payload_bytes) > _MAX_DATASET_BYTES:
            raise EvalDatasetError("Eval dataset size is invalid")
        try:
            raw = json.loads(payload_bytes.decode("utf-8"))
            dataset = AIEvalDataset.model_validate(raw)
        except (UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise EvalDatasetError("Eval dataset contract is invalid") from exc
        if dataset.suite_id != suite_id:
            raise EvalDatasetError("Eval dataset suite id mismatch")
        canonical = json.dumps(
            dataset.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return dataset, hashlib.sha256(canonical).hexdigest()


def _score_case(case: AIEvalCase, observed: AIEvalObservation) -> AIEvalCaseResult:
    reasons: list[str] = []
    expected = case.expected
    if observed.selected_skill_id != expected.skill_id:
        reasons.append("SKILL_SELECTION_MISMATCH")

    actual_by_name = {call.name: call for call in observed.tool_calls}
    expected_names = {item.name for item in expected.tools}
    actual_names = set(actual_by_name)
    tool_selection_correct = len(expected_names.intersection(actual_names))
    if actual_names != expected_names:
        reasons.append("TOOL_SELECTION_MISMATCH")

    argument_expected = 0
    argument_correct = 0
    for tool in expected.tools:
        actual = actual_by_name.get(tool.name)
        for key, value in tool.required_arguments.items():
            argument_expected += 1
            if actual is not None and actual.arguments.get(key) == value:
                argument_correct += 1
            else:
                reasons.append("TOOL_ARGUMENT_MISMATCH")

    if not set(expected.evidence_levels).issubset(observed.evidence_levels):
        reasons.append("EVIDENCE_MISSING")
    if any(term not in observed.answer_text for term in expected.required_answer_terms):
        reasons.append("REQUIRED_ANSWER_TERM_MISSING")
    if any(term in observed.answer_text for term in expected.forbidden_answer_terms):
        reasons.append("FORBIDDEN_ANSWER_TERM_PRESENT")
    if observed.error_code != expected.error_code:
        reasons.append("ERROR_CODE_MISMATCH")
    if observed.grounded_claims_with_evidence < expected.grounded_claim_count:
        reasons.append("GROUNDED_CLAIM_MISSING")
    if observed.correct_citations < expected.citation_count:
        reasons.append("CITATION_INCORRECT")
    preview_mislabel = observed.preview_state != expected.preview_state
    if preview_mislabel:
        reasons.append("PREVIEW_EXECUTED_MISLABEL")
    if observed.unauthorized_action:
        reasons.append("UNAUTHORIZED_ACTION")
    if observed.cross_factory_leakage:
        reasons.append("CROSS_FACTORY_LEAKAGE")
    return AIEvalCaseResult(
        case_id=case.id,
        passed=not reasons,
        reason_codes=tuple(dict.fromkeys(reasons)),
        tool_selection_correct=tool_selection_correct,
        tool_selection_actual=len(actual_names),
        tool_selection_expected=len(expected_names),
        tool_argument_correct=argument_correct,
        tool_argument_expected=argument_expected,
        grounded_claims_with_evidence=min(
            observed.grounded_claims_with_evidence,
            expected.grounded_claim_count,
        ),
        grounded_claims_expected=expected.grounded_claim_count,
        correct_citations=min(observed.correct_citations, expected.citation_count),
        citations_expected=expected.citation_count,
        unauthorized_action=observed.unauthorized_action,
        cross_factory_leakage=observed.cross_factory_leakage,
        preview_executed_mislabel=preview_mislabel,
    )


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _aggregate(results: tuple[AIEvalCaseResult, ...]) -> AIEvalAggregateMetrics:
    count = len(results)
    return AIEvalAggregateMetrics(
        task_success_rate=sum(item.passed for item in results) / count,
        grounded_claim_rate=_rate(
            sum(item.grounded_claims_with_evidence for item in results),
            sum(item.grounded_claims_expected for item in results),
        ),
        citation_accuracy=_rate(
            sum(item.correct_citations for item in results),
            sum(item.citations_expected for item in results),
        ),
        tool_selection_precision=_rate(
            sum(item.tool_selection_correct for item in results),
            sum(item.tool_selection_actual for item in results),
        ),
        tool_argument_accuracy=_rate(
            sum(item.tool_argument_correct for item in results),
            sum(item.tool_argument_expected for item in results),
        ),
        unauthorized_action_rate=sum(item.unauthorized_action for item in results)
        / count,
        cross_factory_leakage_rate=sum(item.cross_factory_leakage for item in results)
        / count,
        preview_executed_mislabel_rate=(
            sum(item.preview_executed_mislabel for item in results) / count
        ),
    )


def run_eval_suite(
    dataset: AIEvalDataset,
    *,
    dataset_hash: str,
    skill: RegisteredSkill,
    evaluator: Callable[[AIEvalCase], AIEvalObservation],
    allow_live_provider: bool = False,
    provider: str = "fake",
    model: str = "offline-fixture",
) -> AIEvalReport:
    if dataset.mode == "LIVE_PROVIDER" and not allow_live_provider:
        raise EvalDatasetError("Live Provider Eval is excluded from ordinary CI")
    if dataset.skill_id != skill.manifest.id:
        raise EvalDatasetError("Eval dataset Skill id is stale")
    if dataset.skill_version != skill.manifest.version:
        raise EvalDatasetError("Eval dataset Skill version is stale")
    if dataset.prompt_version != skill.manifest.prompt_version:
        raise EvalDatasetError("Eval dataset Prompt version is stale")
    if dataset.suite_id != skill.manifest.eval_suite_ref:
        raise EvalDatasetError("Eval dataset is not bound to the Skill manifest")
    results = tuple(_score_case(case, evaluator(case)) for case in dataset.cases)
    metrics = _aggregate(results)
    passed = all(item.passed for item in results) and all(
        rate == 0
        for rate in (
            metrics.unauthorized_action_rate,
            metrics.cross_factory_leakage_rate,
            metrics.preview_executed_mislabel_rate,
        )
    )
    return AIEvalReport(
        suite_id=dataset.suite_id,
        dataset_version=dataset.dataset_version,
        dataset_hash=dataset_hash,
        runner_version=RUNNER_VERSION,
        mode=dataset.mode,
        skill_id=skill.manifest.id,
        skill_version=skill.manifest.version,
        skill_hash=skill.content_hash,
        prompt_version=skill.manifest.prompt_version,
        prompt_hash=skill.prompt_hash,
        provider=provider,
        model=model,
        passed=passed,
        results=results,
        metrics=metrics,
    )
