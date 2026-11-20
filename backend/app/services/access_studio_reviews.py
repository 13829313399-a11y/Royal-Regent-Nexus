"""Atomic link between an explicitly reviewed declaration and a personnel command."""
import json
from uuid import uuid4
from sqlalchemy import select
from app.models.auth import AuthAccessRequest, AuthRoleBindingMetadata, AuthUserPermissionOverride, AuthUserRole
from app.models.identity import EmployeeAssignment, IamOrgDepartment
from app.models.position_review import PositionReview
from app.services import position_reviews as reviews
from app.services.identity_policy import fail
from app.services.identity_resolver import instant, stamp
from app.services.position_workbench_read import load_item


def validate_link(db, actor, row, source, payload, dependencies, scopes):
    link = payload.position_review
    reviews.require_writes()
    review = load_item(db, actor, link.item_key, link.expected_source_revision, pending=True)
    if (not isinstance(review, PositionReview) or review.user_id != row.target_user_id or not source.is_primary
            or review.employment_epoch != source.employment_epoch):
        fail("SOURCE_CHANGED", "岗位申请与办理人员、任职或雇佣周期不一致")
    for pending in db.scalars(select(AuthAccessRequest).where(AuthAccessRequest.target_user_id == row.target_user_id,
            AuthAccessRequest.request_type == "identity:adjust_packages", AuthAccessRequest.lifecycle_state == "pending_approval",
            AuthAccessRequest.id != row.id)):
        other = json.loads(pending.payload_json).get("position_review")
        if other and (other["item_key"], other["expected_source_revision"]) == (link.item_key, link.expected_source_revision):
            fail("ALREADY_SUBMITTED", "该版本的岗位申请已经提交独立审核")
    official = link.confirmed_profile
    org = reviews.validate_position(db, official)
    department = db.get(IamOrgDepartment, (org.id, official.department_code))
    scopes.append((org.id, org.legacy_factory_id, official.department_code))
    dependencies["position_review"] = [review.id, review.revision, review.employment_epoch, org.id, org.revision,
        department.department_code, department.revision]
    return org


def copy_values(row, skip):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns if column.name not in skip}


def continue_assignment(db, row, actor, source, official, at):
    """End the previous formal posting. Keep live source IDs and their exact scopes.

    The old posting retains frozen historical copies for decisions before the
    transfer. Independent grants and other concurrent assignments are untouched.
    """
    next_assignment = EmployeeAssignment(id="assignment-" + uuid4().hex, user_id=source.user_id,
        org_unit_id=official.org_unit_id, department_code=official.department_code, official_position_title=official.position,
        assignment_type=source.assignment_type, is_primary=True, valid_from=at, valid_until=source.valid_until,
        employment_epoch=source.employment_epoch, source_request_id=row.id, created_by=row.requester_user_id,
        confirmed_by=actor.id, created_at=at, updated_at=at)
    source.valid_until, source.ended_reason, source.updated_at = at, row.reason, at
    source.revision += 1
    db.add(next_assignment)
    db.flush()
    continued = {"previous_assignment_id": source.id, "assignment_id": next_assignment.id, "binding_ids": [], "override_ids": []}
    cutoff = instant(at)
    for binding, meta in db.execute(select(AuthUserRole, AuthRoleBindingMetadata).join(AuthRoleBindingMetadata,
            AuthRoleBindingMetadata.user_role_id == AuthUserRole.id).where(AuthUserRole.user_id == row.target_user_id,
            AuthRoleBindingMetadata.assignment_id == source.id, AuthRoleBindingMetadata.state == "active")).all():
        if meta.valid_until and instant(meta.valid_until) <= cutoff:
            continue
        if not meta.valid_from or instant(meta.valid_from) < cutoff:
            archive = AuthUserRole(id="historical-binding-" + uuid4().hex, **copy_values(binding, {"id"}))
            db.add(archive)
            db.flush()
            db.add(AuthRoleBindingMetadata(user_role_id=archive.id, **copy_values(meta, {"user_role_id"})))
        meta.assignment_id = next_assignment.id
        continued["binding_ids"].append(binding.id)
    for override in db.scalars(select(AuthUserPermissionOverride).where(AuthUserPermissionOverride.user_id == row.target_user_id,
            AuthUserPermissionOverride.assignment_id == source.id, AuthUserPermissionOverride.status == "active")).all():
        if override.valid_until and instant(override.valid_until) <= cutoff:
            continue
        if not override.valid_from or instant(override.valid_from) < cutoff:
            db.add(AuthUserPermissionOverride(id="historical-exception-" + uuid4().hex, **copy_values(override, {"id"})))
        override.assignment_id = next_assignment.id
        continued["override_ids"].append(override.id)
    db.flush()
    return next_assignment, continued


def complete_review(db, row, actor, plan):
    link = plan["payload"].position_review
    review = db.get(PositionReview, link.item_key.split(":", 1)[1])
    previous = reviews.review_out(review)
    review.status, review.decision, review.reviewer_user_id = "applied", "adjust_packages", actor.id
    review.confirmed_snapshot_json = json.dumps(link.confirmed_profile.model_dump(), ensure_ascii=False)
    review.applied_identity_change_ids_json = json.dumps([row.id])
    review.receipt_command_id = plan["command_id"]
    review.decision_at = review.updated_at = stamp()
    review.revision += 1
    reviews.event_tx(db, review, actor.id, "applied", previous)
    reviews.notify_tx(db, review, "applied")
