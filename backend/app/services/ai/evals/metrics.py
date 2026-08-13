from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.ai_observability import AIEvalRun
from app.services.ai.evals.contracts import AIEvalReport


def persist_eval_report(
    db: Session,
    report: AIEvalReport,
    *,
    created_by: str = "ci",
) -> AIEvalRun:
    now = business_now().isoformat(timespec="seconds")
    record = AIEvalRun(
        id=f"aiev-{uuid4().hex}",
        suite_id=report.suite_id,
        dataset_version=report.dataset_version,
        dataset_hash=report.dataset_hash,
        runner_version=report.runner_version,
        mode=report.mode,
        skill_id=report.skill_id,
        skill_version=report.skill_version,
        skill_hash=report.skill_hash,
        prompt_version=report.prompt_version,
        prompt_hash=report.prompt_hash,
        provider=report.provider,
        model=report.model,
        status="PASSED" if report.passed else "FAILED",
        case_count=len(report.results),
        passed_count=sum(item.passed for item in report.results),
        failed_count=sum(not item.passed for item in report.results),
        metrics_json=json.dumps(
            report.metrics.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        ),
        created_by=created_by[:64],
        created_at=now,
        completed_at=now,
    )
    db.add(record)
    db.commit()
    return record
