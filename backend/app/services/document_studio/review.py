from __future__ import annotations

from app.schemas.document_studio import (
    DocumentReviewPatch,
    DocumentSnapshot,
)
from app.services.document_studio.contracts import (
    DocumentExtractionSource,
    DocumentReviewAction,
)


class DocumentReviewError(ValueError):
    pass


def apply_review_patches(
    snapshot: DocumentSnapshot,
    *,
    patches: tuple[DocumentReviewPatch, ...],
    issue_targets: dict[str, str],
) -> DocumentSnapshot:
    patch_targets: dict[str, DocumentReviewPatch] = {}
    for patch in patches:
        target = issue_targets.get(patch.issue_id)
        if target is None:
            raise DocumentReviewError("复核项已变化，请刷新后重试。")
        if target in patch_targets:
            raise DocumentReviewError("同一复核目标不能重复提交。")
        patch_targets[target] = patch

    payload = snapshot.model_dump(mode="json")
    found: set[str] = set()
    for page in payload["pages"]:
        for block in page["blocks"]:
            patch = patch_targets.get(block["block_id"])
            if patch is None:
                continue
            found.add(block["block_id"])
            if patch.action == DocumentReviewAction.EDIT:
                block["normalized_text"] = patch.replacement_value
            elif patch.action == DocumentReviewAction.MARK_UNKNOWN:
                block["normalized_text"] = ""
            block["confidence"] = 1.0
            block["source"] = DocumentExtractionSource.USER_REVIEW.value
            block["needs_review"] = False
        for table in page["tables"]:
            for cell in table["cells"]:
                patch = patch_targets.get(cell["cell_id"])
                if patch is None:
                    continue
                found.add(cell["cell_id"])
                if patch.action == DocumentReviewAction.EDIT:
                    cell["normalized_value"] = patch.replacement_value
                elif patch.action == DocumentReviewAction.MARK_UNKNOWN:
                    cell["normalized_value"] = ""
                cell["confidence"] = 1.0
                cell["sources"] = [
                    *cell["sources"],
                    DocumentExtractionSource.USER_REVIEW.value,
                ]
                cell["review_reasons"] = []
    missing = set(patch_targets) - found
    if missing:
        raise DocumentReviewError("复核目标不存在，请刷新后重试。")
    payload["revision"] = snapshot.revision + 1
    return DocumentSnapshot.model_validate(payload)
