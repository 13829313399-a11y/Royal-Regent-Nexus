from pathlib import Path

from app.services.ai.evals.runner import EvalDatasetRegistry

DATASET_ROOT = Path(__file__).resolve().parent / "datasets"


def test_security_action_and_resilience_boundaries_are_versioned() -> None:
    registry = EvalDatasetRegistry(DATASET_ROOT)
    cases = []
    for path in sorted(DATASET_ROOT.glob("*.json")):
        dataset, dataset_hash = registry.load(path.stem)
        assert len(dataset_hash) == 64
        cases.extend(dataset.cases)

    categories = {case.category for case in cases}
    assert {"SECURITY", "ACTION", "RESILIENCE"} <= categories
    tags = {tag for case in cases for tag in case.tags}
    assert {"cross-factory", "kill-switch", "replay"} <= tags
    assert any(case.expected.preview_state == "PREVIEW" for case in cases)
    assert all(case.expected.preview_state != "EXECUTED" for case in cases)
