from __future__ import annotations

from app.services.ai.actions.contracts import ActionApprovalPolicy

APPROVAL_SOURCE_USER_API = "AUTHENTICATED_USER_API"


def validate_approval_source(
    policy: ActionApprovalPolicy,
    *,
    approval_source: str,
    proposer_user_id: str,
    approver_user_id: str,
) -> None:
    if policy.approvals_required != 1:
        raise ValueError("only one explicit approval is supported by the current Pilot")
    if approval_source != policy.allowed_source:
        raise ValueError("approval source is not authorized")
    if policy.approver_must_be_proposer and proposer_user_id != approver_user_id:
        raise ValueError("the current Pilot requires the proposer to approve")
