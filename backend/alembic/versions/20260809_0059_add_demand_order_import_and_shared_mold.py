"""add demand order import and shared mold master data

Revision ID: 20260809_0059
Revises: 20260807_0059
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0059"
down_revision: str | Sequence[str] | None = "20260807_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("injection_scheduling_import_profiles") as batch_op:
        batch_op.add_column(
            sa.Column(
                "document_kind",
                sa.String(32),
                nullable=False,
                server_default="PLANNED_SCHEDULE",
            )
        )
        batch_op.add_column(
            sa.Column(
                "source_namespace_id",
                sa.String(128),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "recognition_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch_op.create_index(
            "ix_injection_scheduling_import_profiles_document_kind",
            ["document_kind"],
        )

    with op.batch_alter_table("injection_scheduling_import_batches") as batch_op:
        batch_op.drop_constraint(
            "ck_injection_scheduling_import_batch_status",
            type_="check",
        )
        batch_op.add_column(
            sa.Column(
                "document_kind",
                sa.String(32),
                nullable=False,
                server_default="PLANNED_SCHEDULE",
            )
        )
        batch_op.add_column(
            sa.Column(
                "source_namespace_id",
                sa.String(128),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "resolution_digest",
                sa.String(64),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "mapping_draft_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch_op.add_column(
            sa.Column("ui_state_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch_op.add_column(
            sa.Column(
                "partial_confirmation_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch_op.add_column(
            sa.Column(
                "artifact_rebind_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.create_check_constraint(
            "ck_injection_scheduling_import_batch_status",
            "status IN ('PREVIEW', 'PARTIALLY_CONFIRMED', 'CONFIRMED')",
        )
        batch_op.create_index(
            "ix_injection_scheduling_import_batches_document_kind",
            ["document_kind"],
        )
        batch_op.create_index(
            "ix_injection_scheduling_import_batches_resolution_digest",
            ["resolution_digest"],
        )

    op.create_table(
        "injection_scheduling_company_scopes",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("code", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("legal_entity_id", sa.String(length=96), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'RETIRED')", name="ck_inj_sched_company_scope_status"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_inj_sched_company_scope_revision"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_inj_sched_company_scope_code"),
    )
    op.create_index(
        op.f("ix_injection_scheduling_company_scopes_code"),
        "injection_scheduling_company_scopes",
        ["code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_company_scopes_created_at"),
        "injection_scheduling_company_scopes",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_company_scopes_legal_entity_id"),
        "injection_scheduling_company_scopes",
        ["legal_entity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_company_scopes_status"),
        "injection_scheduling_company_scopes",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_company_scopes_updated_at"),
        "injection_scheduling_company_scopes",
        ["updated_at"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_demand_order_identities",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("source_namespace_id", sa.String(length=128), nullable=False),
        sa.Column("source_document_id", sa.String(length=128), nullable=False),
        sa.Column("source_order_line_id", sa.String(length=128), nullable=False),
        sa.Column("stable_line_key", sa.String(length=64), nullable=False),
        sa.Column("current_revision_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "factory_id",
            "source_system",
            "source_namespace_id",
            "source_order_line_id",
            name="uq_inj_sched_demand_order_source_line",
        ),
        sa.UniqueConstraint(
            "factory_id", "stable_line_key", name="uq_inj_sched_demand_order_stable_key"
        ),
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_identities_created_at"),
        "injection_scheduling_demand_order_identities",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_identities_factory_id"),
        "injection_scheduling_demand_order_identities",
        ["factory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_identities_source_document_id"),
        "injection_scheduling_demand_order_identities",
        ["source_document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_identities_source_namespace_id"),
        "injection_scheduling_demand_order_identities",
        ["source_namespace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_identities_source_order_line_id"),
        "injection_scheduling_demand_order_identities",
        ["source_order_line_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_identities_source_system"),
        "injection_scheduling_demand_order_identities",
        ["source_system"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_identities_stable_line_key"),
        "injection_scheduling_demand_order_identities",
        ["stable_line_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_identities_status"),
        "injection_scheduling_demand_order_identities",
        ["status"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_master_data_proposals",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=24), nullable=False),
        sa.Column("target_entity_id", sa.String(length=96), nullable=False),
        sa.Column("scope_type", sa.String(length=24), nullable=False),
        sa.Column("scope_id", sa.String(length=96), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("evidence_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("proposed_by", sa.String(length=64), nullable=False),
        sa.Column("proposed_by_name", sa.String(length=128), nullable=False),
        sa.Column("approved_by", sa.String(length=64), nullable=False),
        sa.Column("approved_by_name", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("reviewed_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "action_type IN ('CREATE', 'REVISE', 'MERGE', 'SPLIT', 'RETIRE', 'ALIAS_REDIRECT', 'ACTIVATE')",
            name="ck_inj_sched_master_proposal_action",
        ),
        sa.CheckConstraint(
            "approved_by = '' OR approved_by <> proposed_by",
            name="ck_inj_sched_master_proposal_approval_separation",
        ),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'UNDER_REVIEW', 'APPROVED', 'ACTIVE', 'REJECTED', 'SUPERSEDED', 'RETIRED')",
            name="ck_inj_sched_master_proposal_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scope_type",
            "scope_id",
            "request_id",
            name="uq_inj_sched_master_proposal_request",
        ),
    )
    op.create_index(
        op.f("ix_injection_scheduling_master_data_proposals_action_type"),
        "injection_scheduling_master_data_proposals",
        ["action_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_master_data_proposals_approved_by"),
        "injection_scheduling_master_data_proposals",
        ["approved_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_master_data_proposals_created_at"),
        "injection_scheduling_master_data_proposals",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_master_data_proposals_entity_type"),
        "injection_scheduling_master_data_proposals",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_master_data_proposals_proposed_by"),
        "injection_scheduling_master_data_proposals",
        ["proposed_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_master_data_proposals_request_id"),
        "injection_scheduling_master_data_proposals",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_master_data_proposals_scope_id"),
        "injection_scheduling_master_data_proposals",
        ["scope_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_master_data_proposals_scope_type"),
        "injection_scheduling_master_data_proposals",
        ["scope_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_master_data_proposals_status"),
        "injection_scheduling_master_data_proposals",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_master_data_proposals_target_entity_id"),
        "injection_scheduling_master_data_proposals",
        ["target_entity_id"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_company_factory_memberships",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("company_scope_id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'RETIRED')",
            name="ck_inj_sched_company_factory_status",
        ),
        sa.ForeignKeyConstraint(
            ["company_scope_id"],
            ["injection_scheduling_company_scopes.id"],
            name="fk_inj_sched_company_factory_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("factory_id", name="uq_inj_sched_company_factory"),
    )
    op.create_index(
        op.f("ix_injection_scheduling_company_factory_memberships_company_scope_id"),
        "injection_scheduling_company_factory_memberships",
        ["company_scope_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_company_factory_memberships_created_at"),
        "injection_scheduling_company_factory_memberships",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_company_factory_memberships_factory_id"),
        "injection_scheduling_company_factory_memberships",
        ["factory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_company_factory_memberships_status"),
        "injection_scheduling_company_factory_memberships",
        ["status"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_customer_identities",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("company_scope_id", sa.String(length=96), nullable=False),
        sa.Column("customer_code", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.String(length=96), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'ACTIVE', 'RETIRED')",
            name="ck_inj_sched_customer_status",
        ),
        sa.ForeignKeyConstraint(
            ["company_scope_id"],
            ["injection_scheduling_company_scopes.id"],
            name="fk_inj_sched_customer_company_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_scope_id", "customer_code", name="uq_inj_sched_customer_code"
        ),
    )
    op.create_index(
        op.f("ix_injection_scheduling_customer_identities_company_scope_id"),
        "injection_scheduling_customer_identities",
        ["company_scope_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_customer_identities_created_at"),
        "injection_scheduling_customer_identities",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_customer_identities_customer_code"),
        "injection_scheduling_customer_identities",
        ["customer_code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_customer_identities_proposal_id"),
        "injection_scheduling_customer_identities",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_customer_identities_status"),
        "injection_scheduling_customer_identities",
        ["status"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_demand_import_rows",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("batch_id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("preview_generation", sa.Integer(), nullable=False),
        sa.Column("source_sheet_name", sa.String(length=128), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_order_line_id", sa.String(length=128), nullable=False),
        sa.Column("source_revision", sa.String(length=128), nullable=False),
        sa.Column("stable_line_key", sa.String(length=64), nullable=False),
        sa.Column("identity_quality", sa.String(length=32), nullable=False),
        sa.Column("canonical_json", sa.Text(), nullable=False),
        sa.Column("source_lineage_json", sa.Text(), nullable=False),
        sa.Column("resolution_status", sa.String(length=32), nullable=False),
        sa.Column("confirmation_state", sa.String(length=24), nullable=False),
        sa.Column("row_digest", sa.String(length=64), nullable=False),
        sa.Column("confirmed_generation", sa.Integer(), nullable=True),
        sa.Column("confirmed_order_identity_id", sa.String(length=96), nullable=False),
        sa.Column("confirmed_order_version_id", sa.String(length=96), nullable=False),
        sa.Column(
            "confirmed_plan_order_state_id", sa.String(length=96), nullable=False
        ),
        sa.Column("confirm_request_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "confirmation_state IN ('PENDING', 'CONFIRMED', 'SKIPPED', 'RETAINED_FINAL')",
            name="ck_inj_sched_demand_import_row_confirmation",
        ),
        sa.CheckConstraint(
            "resolution_status IN ('READY', 'AUTO_CONFIRMED', 'REVIEW_REQUIRED', 'IDENTITY_REVIEW_REQUIRED', 'AMBIGUOUS', 'NOT_FOUND', 'PRICE_REVIEW_REQUIRED', 'CONFLICT', 'INVALID', 'DUPLICATE', 'UPDATE', 'REMOVAL_REVIEW')",
            name="ck_inj_sched_demand_import_row_resolution",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_inj_sched_demand_import_row_batch",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id",
            "preview_generation",
            "source_sheet_name",
            "source_row",
            name="uq_inj_sched_demand_import_row_source",
        ),
    )
    op.create_index(
        "ix_inj_sched_demand_import_row_batch_status",
        "injection_scheduling_demand_import_rows",
        ["batch_id", "preview_generation", "resolution_status", "confirmation_state"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_import_rows_batch_id"),
        "injection_scheduling_demand_import_rows",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_import_rows_confirm_request_id"),
        "injection_scheduling_demand_import_rows",
        ["confirm_request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_import_rows_confirmation_state"),
        "injection_scheduling_demand_import_rows",
        ["confirmation_state"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_import_rows_created_at"),
        "injection_scheduling_demand_import_rows",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_import_rows_factory_id"),
        "injection_scheduling_demand_import_rows",
        ["factory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_import_rows_preview_generation"),
        "injection_scheduling_demand_import_rows",
        ["preview_generation"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_import_rows_resolution_status"),
        "injection_scheduling_demand_import_rows",
        ["resolution_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_import_rows_row_digest"),
        "injection_scheduling_demand_import_rows",
        ["row_digest"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_import_rows_stable_line_key"),
        "injection_scheduling_demand_import_rows",
        ["stable_line_key"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_field_evidence",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("proposal_id", sa.String(length=96), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=96), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column("source_file_hash", sa.String(length=64), nullable=False),
        sa.Column("sheet_name", sa.String(length=128), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("cell_ref", sa.String(length=32), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=False),
        sa.Column("displayed_value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=24), nullable=False),
        sa.Column("submitted_by", sa.String(length=64), nullable=False),
        sa.Column("approved_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["injection_scheduling_master_data_proposals.id"],
            name="fk_inj_sched_field_evidence_proposal",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inj_sched_field_evidence_entity_field",
        "injection_scheduling_field_evidence",
        ["entity_type", "entity_id", "field_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_field_evidence_created_at"),
        "injection_scheduling_field_evidence",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_field_evidence_entity_id"),
        "injection_scheduling_field_evidence",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_field_evidence_entity_type"),
        "injection_scheduling_field_evidence",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_field_evidence_field_name"),
        "injection_scheduling_field_evidence",
        ["field_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_field_evidence_proposal_id"),
        "injection_scheduling_field_evidence",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_field_evidence_source_file_hash"),
        "injection_scheduling_field_evidence",
        ["source_file_hash"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_mold_definitions",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("company_scope_id", sa.String(length=96), nullable=False),
        sa.Column("canonical_mold_no", sa.String(length=128), nullable=False),
        sa.Column("display_mold_no", sa.String(length=128), nullable=False),
        sa.Column("standard_name", sa.String(length=255), nullable=False),
        sa.Column(
            "recommended_machine_class_raw", sa.String(length=128), nullable=False
        ),
        sa.Column("mold_a_class", sa.Integer(), nullable=True),
        sa.Column("default_arm_type", sa.String(length=64), nullable=False),
        sa.Column("default_fixture_type", sa.String(length=64), nullable=False),
        sa.Column("process_tags_json", sa.Text(), nullable=False),
        sa.Column("engineering_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("data_quality", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.String(length=32), nullable=False),
        sa.Column("valid_to", sa.String(length=32), nullable=False),
        sa.Column("proposal_id", sa.String(length=96), nullable=False),
        sa.Column("created_factory_id", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("approved_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("approved_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'UNDER_REVIEW', 'ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="ck_inj_sched_mold_definition_status",
        ),
        sa.CheckConstraint(
            "mold_a_class IS NULL OR mold_a_class > 0",
            name="ck_inj_sched_mold_definition_a_class",
        ),
        sa.ForeignKeyConstraint(
            ["company_scope_id"],
            ["injection_scheduling_company_scopes.id"],
            name="fk_inj_sched_mold_definition_company_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_scope_id",
            "canonical_mold_no",
            name="uq_inj_sched_mold_definition_number",
        ),
    )
    op.create_index(
        "ix_inj_sched_mold_definition_company_status",
        "injection_scheduling_mold_definitions",
        ["company_scope_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_definitions_canonical_mold_no"),
        "injection_scheduling_mold_definitions",
        ["canonical_mold_no"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_definitions_company_scope_id"),
        "injection_scheduling_mold_definitions",
        ["company_scope_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_definitions_created_at"),
        "injection_scheduling_mold_definitions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_definitions_created_factory_id"),
        "injection_scheduling_mold_definitions",
        ["created_factory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_definitions_mold_a_class"),
        "injection_scheduling_mold_definitions",
        ["mold_a_class"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_definitions_proposal_id"),
        "injection_scheduling_mold_definitions",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_definitions_status"),
        "injection_scheduling_mold_definitions",
        ["status"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_customer_aliases",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("company_scope_id", sa.String(length=96), nullable=False),
        sa.Column("customer_identity_id", sa.String(length=96), nullable=False),
        sa.Column("source_namespace_id", sa.String(length=128), nullable=False),
        sa.Column("raw_alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("valid_from", sa.String(length=32), nullable=False),
        sa.Column("valid_to", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.String(length=96), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="ck_inj_sched_customer_alias_status",
        ),
        sa.ForeignKeyConstraint(
            ["company_scope_id"],
            ["injection_scheduling_company_scopes.id"],
            name="fk_inj_sched_customer_alias_company_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_identity_id"],
            ["injection_scheduling_customer_identities.id"],
            name="fk_inj_sched_customer_alias_identity",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_scope_id",
            "source_namespace_id",
            "normalized_alias",
            "valid_from",
            name="uq_inj_sched_customer_alias_effective",
        ),
    )
    op.create_index(
        op.f("ix_injection_scheduling_customer_aliases_company_scope_id"),
        "injection_scheduling_customer_aliases",
        ["company_scope_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_customer_aliases_created_at"),
        "injection_scheduling_customer_aliases",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_customer_aliases_customer_identity_id"),
        "injection_scheduling_customer_aliases",
        ["customer_identity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_customer_aliases_normalized_alias"),
        "injection_scheduling_customer_aliases",
        ["normalized_alias"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_customer_aliases_proposal_id"),
        "injection_scheduling_customer_aliases",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_customer_aliases_source_namespace_id"),
        "injection_scheduling_customer_aliases",
        ["source_namespace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_customer_aliases_status"),
        "injection_scheduling_customer_aliases",
        ["status"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_demand_resolution_snapshots",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("demand_import_row_id", sa.String(length=96), nullable=False),
        sa.Column("preview_generation", sa.Integer(), nullable=False),
        sa.Column("resolution_status", sa.String(length=32), nullable=False),
        sa.Column("mold_definition_id", sa.String(length=96), nullable=True),
        sa.Column("mold_output_spec_id", sa.String(length=96), nullable=True),
        sa.Column("physical_mold_asset_id", sa.String(length=96), nullable=True),
        sa.Column("factory_capability_id", sa.String(length=96), nullable=True),
        sa.Column("commercial_rate_rule_id", sa.String(length=96), nullable=True),
        sa.Column("master_revision_digest", sa.String(length=64), nullable=False),
        sa.Column("resolution_digest", sa.String(length=64), nullable=False),
        sa.Column("resolved_values_json", sa.Text(), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("candidate_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["demand_import_row_id"],
            ["injection_scheduling_demand_import_rows.id"],
            name="fk_inj_sched_demand_resolution_row",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "demand_import_row_id",
            "preview_generation",
            name="uq_inj_sched_demand_resolution_generation",
        ),
    )
    op.create_index(
        op.f(
            "ix_injection_scheduling_demand_resolution_snapshots_commercial_rate_rule_id"
        ),
        "injection_scheduling_demand_resolution_snapshots",
        ["commercial_rate_rule_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_resolution_snapshots_created_at"),
        "injection_scheduling_demand_resolution_snapshots",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f(
            "ix_injection_scheduling_demand_resolution_snapshots_demand_import_row_id"
        ),
        "injection_scheduling_demand_resolution_snapshots",
        ["demand_import_row_id"],
        unique=False,
    )
    op.create_index(
        op.f(
            "ix_injection_scheduling_demand_resolution_snapshots_factory_capability_id"
        ),
        "injection_scheduling_demand_resolution_snapshots",
        ["factory_capability_id"],
        unique=False,
    )
    op.create_index(
        op.f(
            "ix_injection_scheduling_demand_resolution_snapshots_master_revision_digest"
        ),
        "injection_scheduling_demand_resolution_snapshots",
        ["master_revision_digest"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_resolution_snapshots_mold_definition_id"),
        "injection_scheduling_demand_resolution_snapshots",
        ["mold_definition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_resolution_snapshots_mold_output_spec_id"),
        "injection_scheduling_demand_resolution_snapshots",
        ["mold_output_spec_id"],
        unique=False,
    )
    op.create_index(
        op.f(
            "ix_injection_scheduling_demand_resolution_snapshots_physical_mold_asset_id"
        ),
        "injection_scheduling_demand_resolution_snapshots",
        ["physical_mold_asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_resolution_snapshots_preview_generation"),
        "injection_scheduling_demand_resolution_snapshots",
        ["preview_generation"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_resolution_snapshots_resolution_digest"),
        "injection_scheduling_demand_resolution_snapshots",
        ["resolution_digest"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_resolution_snapshots_resolution_status"),
        "injection_scheduling_demand_resolution_snapshots",
        ["resolution_status"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_mold_aliases",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("company_scope_id", sa.String(length=96), nullable=False),
        sa.Column("source_namespace_id", sa.String(length=128), nullable=False),
        sa.Column("namespace_type", sa.String(length=32), nullable=False),
        sa.Column("raw_alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("mold_definition_id", sa.String(length=96), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.String(length=32), nullable=False),
        sa.Column("valid_to", sa.String(length=32), nullable=False),
        sa.Column("proposal_id", sa.String(length=96), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'UNDER_REVIEW', 'ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="ck_inj_sched_mold_alias_status",
        ),
        sa.ForeignKeyConstraint(
            ["company_scope_id"],
            ["injection_scheduling_company_scopes.id"],
            name="fk_inj_sched_mold_alias_company_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mold_definition_id"],
            ["injection_scheduling_mold_definitions.id"],
            name="fk_inj_sched_mold_alias_definition",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_scope_id",
            "source_namespace_id",
            "normalized_alias",
            "valid_from",
            name="uq_inj_sched_mold_alias_effective",
        ),
    )
    op.create_index(
        "ix_inj_sched_mold_alias_lookup",
        "injection_scheduling_mold_aliases",
        ["company_scope_id", "source_namespace_id", "normalized_alias", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_aliases_company_scope_id"),
        "injection_scheduling_mold_aliases",
        ["company_scope_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_aliases_created_at"),
        "injection_scheduling_mold_aliases",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_aliases_mold_definition_id"),
        "injection_scheduling_mold_aliases",
        ["mold_definition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_aliases_normalized_alias"),
        "injection_scheduling_mold_aliases",
        ["normalized_alias"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_aliases_proposal_id"),
        "injection_scheduling_mold_aliases",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_aliases_source_namespace_id"),
        "injection_scheduling_mold_aliases",
        ["source_namespace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_aliases_status"),
        "injection_scheduling_mold_aliases",
        ["status"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_mold_output_specs",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("mold_definition_id", sa.String(length=96), nullable=False),
        sa.Column("customer_identity_id", sa.String(length=96), nullable=True),
        sa.Column("item_no", sa.String(length=128), nullable=False),
        sa.Column("variant_code", sa.String(length=128), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("cavity_count", sa.Integer(), nullable=True),
        sa.Column("units_per_shot", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column(
            "whole_shot_net_weight_g", sa.Numeric(precision=14, scale=4), nullable=True
        ),
        sa.Column(
            "whole_shot_gross_weight_g",
            sa.Numeric(precision=14, scale=4),
            nullable=True,
        ),
        sa.Column("default_material", sa.String(length=255), nullable=False),
        sa.Column("default_color", sa.String(length=128), nullable=False),
        sa.Column(
            "nominal_cycle_seconds", sa.Numeric(precision=14, scale=4), nullable=True
        ),
        sa.Column(
            "nominal_daily_capacity", sa.Numeric(precision=14, scale=3), nullable=True
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.String(length=32), nullable=False),
        sa.Column("valid_to", sa.String(length=32), nullable=False),
        sa.Column("proposal_id", sa.String(length=96), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'UNDER_REVIEW', 'ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="ck_inj_sched_mold_output_status",
        ),
        sa.ForeignKeyConstraint(
            ["customer_identity_id"],
            ["injection_scheduling_customer_identities.id"],
            name="fk_inj_sched_mold_output_customer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mold_definition_id"],
            ["injection_scheduling_mold_definitions.id"],
            name="fk_inj_sched_mold_output_definition",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mold_definition_id",
            "customer_identity_id",
            "item_no",
            "variant_code",
            "valid_from",
            name="uq_inj_sched_mold_output_effective",
        ),
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_output_specs_created_at"),
        "injection_scheduling_mold_output_specs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_output_specs_customer_identity_id"),
        "injection_scheduling_mold_output_specs",
        ["customer_identity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_output_specs_item_no"),
        "injection_scheduling_mold_output_specs",
        ["item_no"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_output_specs_mold_definition_id"),
        "injection_scheduling_mold_output_specs",
        ["mold_definition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_output_specs_proposal_id"),
        "injection_scheduling_mold_output_specs",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_output_specs_status"),
        "injection_scheduling_mold_output_specs",
        ["status"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_physical_mold_assets",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("mold_definition_id", sa.String(length=96), nullable=False),
        sa.Column("owner_scope_type", sa.String(length=24), nullable=False),
        sa.Column("owner_scope_id", sa.String(length=96), nullable=False),
        sa.Column("asset_code", sa.String(length=128), nullable=False),
        sa.Column("serial_no", sa.String(length=128), nullable=False),
        sa.Column("current_factory_id", sa.String(length=64), nullable=False),
        sa.Column("current_location", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("actual_cavity_count", sa.Integer(), nullable=True),
        sa.Column("available_from", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source_mold_id", sa.String(length=96), nullable=True),
        sa.Column("source_copy_no", sa.Integer(), nullable=True),
        sa.Column("verified_by", sa.String(length=64), nullable=False),
        sa.Column("verified_at", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "owner_scope_type IN ('COMPANY', 'FACTORY', 'LEGAL_ENTITY')",
            name="ck_inj_sched_mold_asset_owner_scope",
        ),
        sa.CheckConstraint(
            "status IN ('LEGACY_UNVERIFIED', 'AVAILABLE', 'MAINTENANCE', 'LOANED', 'IN_TRANSIT', 'RETIRED')",
            name="ck_inj_sched_mold_asset_status",
        ),
        sa.ForeignKeyConstraint(
            ["mold_definition_id"],
            ["injection_scheduling_mold_definitions.id"],
            name="fk_inj_sched_mold_asset_definition",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_scope_type",
            "owner_scope_id",
            "asset_code",
            name="uq_inj_sched_mold_asset_code",
        ),
    )
    op.create_index(
        "ix_inj_sched_mold_asset_factory_status",
        "injection_scheduling_physical_mold_assets",
        ["current_factory_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_physical_mold_assets_asset_code"),
        "injection_scheduling_physical_mold_assets",
        ["asset_code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_physical_mold_assets_created_at"),
        "injection_scheduling_physical_mold_assets",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_physical_mold_assets_current_factory_id"),
        "injection_scheduling_physical_mold_assets",
        ["current_factory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_physical_mold_assets_mold_definition_id"),
        "injection_scheduling_physical_mold_assets",
        ["mold_definition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_physical_mold_assets_owner_scope_id"),
        "injection_scheduling_physical_mold_assets",
        ["owner_scope_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_physical_mold_assets_source_mold_id"),
        "injection_scheduling_physical_mold_assets",
        ["source_mold_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_physical_mold_assets_status"),
        "injection_scheduling_physical_mold_assets",
        ["status"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_commercial_rate_rules",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("owner_scope_type", sa.String(length=24), nullable=False),
        sa.Column("owner_scope_id", sa.String(length=96), nullable=False),
        sa.Column("applicable_factory_mode", sa.String(length=40), nullable=False),
        sa.Column("applicable_factory_id", sa.String(length=64), nullable=True),
        sa.Column("applicable_customer_mode", sa.String(length=16), nullable=False),
        sa.Column("applicable_customer_id", sa.String(length=96), nullable=True),
        sa.Column("mold_definition_id", sa.String(length=96), nullable=True),
        sa.Column("mold_output_spec_id", sa.String(length=96), nullable=True),
        sa.Column("contract_mode", sa.String(length=16), nullable=False),
        sa.Column("contract_id", sa.String(length=128), nullable=True),
        sa.Column("pricing_basis", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("tax_mode", sa.String(length=32), nullable=False),
        sa.Column("quantity_min", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("quantity_max", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.String(length=32), nullable=False),
        sa.Column("valid_to", sa.String(length=32), nullable=False),
        sa.Column("proposal_id", sa.String(length=96), nullable=False),
        sa.Column("proposed_by", sa.String(length=64), nullable=False),
        sa.Column("approved_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("approved_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "applicable_customer_mode IN ('SPECIFIC', 'ANY')",
            name="ck_inj_sched_rate_customer_mode",
        ),
        sa.CheckConstraint(
            "applicable_factory_mode IN ('SPECIFIC', 'ANY_IN_OWNER_COMPANY', 'ANY_IN_OWNER_LEGAL_ENTITY')",
            name="ck_inj_sched_rate_factory_mode",
        ),
        sa.CheckConstraint(
            "owner_scope_type IN ('COMPANY', 'FACTORY', 'LEGAL_ENTITY')",
            name="ck_inj_sched_rate_owner_scope",
        ),
        sa.CheckConstraint(
            "pricing_basis IN ('PER_SHOT', 'PER_PIECE', 'PER_SET', 'PER_HOUR')",
            name="ck_inj_sched_rate_pricing_basis",
        ),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'UNDER_REVIEW', 'APPROVED', 'ACTIVE', 'SUPERSEDED', 'RETIRED', 'REJECTED')",
            name="ck_inj_sched_rate_status",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_inj_sched_rate_amount"),
        sa.CheckConstraint(
            "(applicable_factory_mode = 'SPECIFIC' AND applicable_factory_id IS NOT NULL) "
            "OR (applicable_factory_mode <> 'SPECIFIC' AND applicable_factory_id IS NULL)",
            name="ck_inj_sched_rate_factory_scope_shape",
        ),
        sa.CheckConstraint(
            "(applicable_customer_mode = 'SPECIFIC' AND applicable_customer_id IS NOT NULL) "
            "OR (applicable_customer_mode = 'ANY' AND applicable_customer_id IS NULL)",
            name="ck_inj_sched_rate_customer_scope_shape",
        ),
        sa.CheckConstraint(
            "(contract_mode = 'SPECIFIC' AND contract_id IS NOT NULL) "
            "OR (contract_mode = 'ANY' AND contract_id IS NULL)",
            name="ck_inj_sched_rate_contract_scope_shape",
        ),
        sa.CheckConstraint(
            "owner_scope_type <> 'FACTORY' OR "
            "(applicable_factory_mode = 'SPECIFIC' AND owner_scope_id = applicable_factory_id)",
            name="ck_inj_sched_rate_factory_owner_scope",
        ),
        sa.CheckConstraint(
            "quantity_min IS NULL OR quantity_min >= 0",
            name="ck_inj_sched_rate_quantity_min",
        ),
        sa.CheckConstraint(
            "quantity_max IS NULL OR quantity_max >= 0",
            name="ck_inj_sched_rate_quantity_max",
        ),
        sa.CheckConstraint(
            "quantity_min IS NULL OR quantity_max IS NULL OR quantity_min <= quantity_max",
            name="ck_inj_sched_rate_quantity_range",
        ),
        sa.CheckConstraint(
            "approved_by = '' OR proposed_by = '' OR approved_by <> proposed_by",
            name="ck_inj_sched_rate_approval_separation",
        ),
        sa.ForeignKeyConstraint(
            ["applicable_customer_id"],
            ["injection_scheduling_customer_identities.id"],
            name="fk_inj_sched_rate_customer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mold_definition_id"],
            ["injection_scheduling_mold_definitions.id"],
            name="fk_inj_sched_rate_definition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mold_output_spec_id"],
            ["injection_scheduling_mold_output_specs.id"],
            name="fk_inj_sched_rate_output",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inj_sched_rate_resolution",
        "injection_scheduling_commercial_rate_rules",
        [
            "status",
            "applicable_factory_id",
            "applicable_customer_id",
            "mold_output_spec_id",
            "valid_from",
        ],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_commercial_rate_rules_applicable_customer_id"),
        "injection_scheduling_commercial_rate_rules",
        ["applicable_customer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_commercial_rate_rules_applicable_factory_id"),
        "injection_scheduling_commercial_rate_rules",
        ["applicable_factory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_commercial_rate_rules_created_at"),
        "injection_scheduling_commercial_rate_rules",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_commercial_rate_rules_mold_definition_id"),
        "injection_scheduling_commercial_rate_rules",
        ["mold_definition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_commercial_rate_rules_mold_output_spec_id"),
        "injection_scheduling_commercial_rate_rules",
        ["mold_output_spec_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_commercial_rate_rules_owner_scope_id"),
        "injection_scheduling_commercial_rate_rules",
        ["owner_scope_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_commercial_rate_rules_proposal_id"),
        "injection_scheduling_commercial_rate_rules",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_commercial_rate_rules_status"),
        "injection_scheduling_commercial_rate_rules",
        ["status"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_demand_order_versions",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("order_identity_id", sa.String(length=96), nullable=False),
        sa.Column("source_revision", sa.String(length=128), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("customer_identity_id", sa.String(length=96), nullable=True),
        sa.Column("source_document_no", sa.String(length=128), nullable=False),
        sa.Column("item_no", sa.String(length=128), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("mold_definition_id", sa.String(length=96), nullable=True),
        sa.Column("mold_output_spec_id", sa.String(length=96), nullable=True),
        sa.Column("factory_mold_id", sa.String(length=96), nullable=True),
        sa.Column("order_quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("set_quantity", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("required_shots", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("delivery_due_date", sa.String(length=32), nullable=False),
        sa.Column("warehouse_text", sa.String(length=255), nullable=False),
        sa.Column("material_name", sa.String(length=255), nullable=False),
        sa.Column("color_name", sa.String(length=128), nullable=False),
        sa.Column("remark", sa.Text(), nullable=False),
        sa.Column("readiness_status", sa.String(length=32), nullable=False),
        sa.Column("commercial_rate_rule_id", sa.String(length=96), nullable=True),
        sa.Column("frozen_amount", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("frozen_currency", sa.String(length=8), nullable=False),
        sa.Column("frozen_pricing_basis", sa.String(length=16), nullable=False),
        sa.Column("canonical_json", sa.Text(), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("source_lineage_json", sa.Text(), nullable=False),
        sa.Column("version_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'CANCELLED')",
            name="ck_inj_sched_demand_version_status",
        ),
        sa.ForeignKeyConstraint(
            ["mold_definition_id"],
            ["injection_scheduling_mold_definitions.id"],
            name="fk_inj_sched_demand_version_definition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mold_output_spec_id"],
            ["injection_scheduling_mold_output_specs.id"],
            name="fk_inj_sched_demand_version_output",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_identity_id"],
            ["injection_scheduling_demand_order_identities.id"],
            name="fk_inj_sched_demand_version_identity",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_identity_id",
            "source_revision",
            name="uq_inj_sched_demand_version_revision",
        ),
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_commercial_rate_rule_id"),
        "injection_scheduling_demand_order_versions",
        ["commercial_rate_rule_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_created_at"),
        "injection_scheduling_demand_order_versions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_customer_identity_id"),
        "injection_scheduling_demand_order_versions",
        ["customer_identity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_delivery_due_date"),
        "injection_scheduling_demand_order_versions",
        ["delivery_due_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_factory_mold_id"),
        "injection_scheduling_demand_order_versions",
        ["factory_mold_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_item_no"),
        "injection_scheduling_demand_order_versions",
        ["item_no"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_mold_definition_id"),
        "injection_scheduling_demand_order_versions",
        ["mold_definition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_mold_output_spec_id"),
        "injection_scheduling_demand_order_versions",
        ["mold_output_spec_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_order_identity_id"),
        "injection_scheduling_demand_order_versions",
        ["order_identity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_readiness_status"),
        "injection_scheduling_demand_order_versions",
        ["readiness_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_source_document_no"),
        "injection_scheduling_demand_order_versions",
        ["source_document_no"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_source_revision"),
        "injection_scheduling_demand_order_versions",
        ["source_revision"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_status"),
        "injection_scheduling_demand_order_versions",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_demand_order_versions_version_digest"),
        "injection_scheduling_demand_order_versions",
        ["version_digest"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_factory_mold_capabilities",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("mold_definition_id", sa.String(length=96), nullable=False),
        sa.Column("mold_output_spec_id", sa.String(length=96), nullable=True),
        sa.Column("physical_asset_id", sa.String(length=96), nullable=True),
        sa.Column("machine_class", sa.Integer(), nullable=True),
        sa.Column("applicability_key", sa.String(length=64), nullable=False),
        sa.Column("required_arm_type", sa.String(length=64), nullable=False),
        sa.Column("required_fixture_type", sa.String(length=64), nullable=False),
        sa.Column("process_limits_json", sa.Text(), nullable=False),
        sa.Column(
            "nominal_cycle_seconds", sa.Numeric(precision=14, scale=4), nullable=True
        ),
        sa.Column(
            "nominal_daily_capacity", sa.Numeric(precision=14, scale=3), nullable=True
        ),
        sa.Column("setup_minutes", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.String(length=32), nullable=False),
        sa.Column("valid_to", sa.String(length=32), nullable=False),
        sa.Column("proposal_id", sa.String(length=96), nullable=False),
        sa.Column("approved_by", sa.String(length=64), nullable=False),
        sa.Column("approved_at", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'UNDER_REVIEW', 'ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="ck_inj_sched_factory_capability_status",
        ),
        sa.ForeignKeyConstraint(
            ["mold_definition_id"],
            ["injection_scheduling_mold_definitions.id"],
            name="fk_inj_sched_factory_capability_definition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mold_output_spec_id"],
            ["injection_scheduling_mold_output_specs.id"],
            name="fk_inj_sched_factory_capability_output",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["physical_asset_id"],
            ["injection_scheduling_physical_mold_assets.id"],
            name="fk_inj_sched_factory_capability_asset",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "factory_id",
            "applicability_key",
            "priority",
            "valid_from",
            name="uq_inj_sched_factory_capability_effective",
        ),
    )
    op.create_index(
        op.f("ix_injection_scheduling_factory_mold_capabilities_applicability_key"),
        "injection_scheduling_factory_mold_capabilities",
        ["applicability_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_factory_mold_capabilities_created_at"),
        "injection_scheduling_factory_mold_capabilities",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_factory_mold_capabilities_factory_id"),
        "injection_scheduling_factory_mold_capabilities",
        ["factory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_factory_mold_capabilities_mold_definition_id"),
        "injection_scheduling_factory_mold_capabilities",
        ["mold_definition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_factory_mold_capabilities_mold_output_spec_id"),
        "injection_scheduling_factory_mold_capabilities",
        ["mold_output_spec_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_factory_mold_capabilities_physical_asset_id"),
        "injection_scheduling_factory_mold_capabilities",
        ["physical_asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_factory_mold_capabilities_proposal_id"),
        "injection_scheduling_factory_mold_capabilities",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_factory_mold_capabilities_status"),
        "injection_scheduling_factory_mold_capabilities",
        ["status"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_legacy_mold_copy_bindings",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("mold_id", sa.String(length=96), nullable=False),
        sa.Column("mold_copy_no", sa.Integer(), nullable=False),
        sa.Column("physical_asset_id", sa.String(length=96), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("activated_by", sa.String(length=64), nullable=False),
        sa.Column("activated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["physical_asset_id"],
            ["injection_scheduling_physical_mold_assets.id"],
            name="fk_inj_sched_legacy_binding_asset",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "factory_id",
            "mold_id",
            "mold_copy_no",
            name="uq_inj_sched_legacy_mold_copy",
        ),
        sa.UniqueConstraint(
            "physical_asset_id", name="uq_inj_sched_legacy_physical_asset"
        ),
    )
    op.create_index(
        op.f("ix_injection_scheduling_legacy_mold_copy_bindings_activated_at"),
        "injection_scheduling_legacy_mold_copy_bindings",
        ["activated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_legacy_mold_copy_bindings_factory_id"),
        "injection_scheduling_legacy_mold_copy_bindings",
        ["factory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_legacy_mold_copy_bindings_mold_id"),
        "injection_scheduling_legacy_mold_copy_bindings",
        ["mold_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_legacy_mold_copy_bindings_physical_asset_id"),
        "injection_scheduling_legacy_mold_copy_bindings",
        ["physical_asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_legacy_mold_copy_bindings_status"),
        "injection_scheduling_legacy_mold_copy_bindings",
        ["status"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_mold_asset_movements",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("physical_asset_id", sa.String(length=96), nullable=False),
        sa.Column("movement_type", sa.String(length=32), nullable=False),
        sa.Column("from_factory_id", sa.String(length=64), nullable=False),
        sa.Column("to_factory_id", sa.String(length=64), nullable=False),
        sa.Column("from_location", sa.String(length=255), nullable=False),
        sa.Column("to_location", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("effective_at", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('PLANNED', 'APPROVED', 'EFFECTIVE', 'CANCELLED')",
            name="ck_inj_sched_mold_movement_status",
        ),
        sa.ForeignKeyConstraint(
            ["physical_asset_id"],
            ["injection_scheduling_physical_mold_assets.id"],
            name="fk_inj_sched_mold_movement_asset",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "physical_asset_id", "request_id", name="uq_inj_sched_mold_movement_request"
        ),
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_asset_movements_created_at"),
        "injection_scheduling_mold_asset_movements",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_asset_movements_effective_at"),
        "injection_scheduling_mold_asset_movements",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_asset_movements_from_factory_id"),
        "injection_scheduling_mold_asset_movements",
        ["from_factory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_asset_movements_physical_asset_id"),
        "injection_scheduling_mold_asset_movements",
        ["physical_asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_asset_movements_request_id"),
        "injection_scheduling_mold_asset_movements",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_asset_movements_status"),
        "injection_scheduling_mold_asset_movements",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_asset_movements_to_factory_id"),
        "injection_scheduling_mold_asset_movements",
        ["to_factory_id"],
        unique=False,
    )
    op.create_table(
        "injection_scheduling_mold_reservations",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("physical_asset_id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("plan_id", sa.String(length=96), nullable=False),
        sa.Column("task_id", sa.String(length=96), nullable=True),
        sa.Column("window_start", sa.String(length=32), nullable=False),
        sa.Column("window_end", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("released_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('TENTATIVE', 'ACTIVE', 'RELEASED', 'CANCELLED', 'EXPIRED')",
            name="ck_inj_sched_mold_reservation_status",
        ),
        sa.CheckConstraint(
            "window_end > window_start", name="ck_inj_sched_mold_reservation_window"
        ),
        sa.ForeignKeyConstraint(
            ["physical_asset_id"],
            ["injection_scheduling_physical_mold_assets.id"],
            name="fk_inj_sched_mold_reservation_asset",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "factory_id", "idempotency_key", name="uq_inj_sched_mold_reservation_key"
        ),
    )
    op.create_index(
        "ix_inj_sched_mold_reservation_asset_window",
        "injection_scheduling_mold_reservations",
        ["physical_asset_id", "window_start", "window_end", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_reservations_created_at"),
        "injection_scheduling_mold_reservations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_reservations_expires_at"),
        "injection_scheduling_mold_reservations",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_reservations_factory_id"),
        "injection_scheduling_mold_reservations",
        ["factory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_reservations_idempotency_key"),
        "injection_scheduling_mold_reservations",
        ["idempotency_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_reservations_physical_asset_id"),
        "injection_scheduling_mold_reservations",
        ["physical_asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_reservations_plan_id"),
        "injection_scheduling_mold_reservations",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_reservations_status"),
        "injection_scheduling_mold_reservations",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_reservations_task_id"),
        "injection_scheduling_mold_reservations",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_reservations_window_end"),
        "injection_scheduling_mold_reservations",
        ["window_end"],
        unique=False,
    )
    op.create_index(
        op.f("ix_injection_scheduling_mold_reservations_window_start"),
        "injection_scheduling_mold_reservations",
        ["window_start"],
        unique=False,
    )

    with op.batch_alter_table("injection_scheduling_molds") as batch_op:
        batch_op.add_column(sa.Column("definition_id", sa.String(96), nullable=True))
        batch_op.create_foreign_key(
            "fk_inj_sched_mold_shared_definition",
            "injection_scheduling_mold_definitions",
            ["definition_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_injection_scheduling_molds_definition_id",
            ["definition_id"],
        )

    with op.batch_alter_table("injection_scheduling_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("physical_mold_asset_id", sa.String(96), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_inj_sched_task_physical_mold_asset",
            "injection_scheduling_physical_mold_assets",
            ["physical_mold_asset_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_injection_scheduling_tasks_physical_mold_asset_id",
            ["physical_mold_asset_id"],
        )

    with op.batch_alter_table("injection_scheduling_plan_order_states") as batch_op:
        batch_op.add_column(
            sa.Column("order_revision_id", sa.String(96), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "factory_readiness_status",
                sa.String(32),
                nullable=False,
                server_default="LEGACY_UNKNOWN",
            )
        )
        batch_op.create_foreign_key(
            "fk_inj_sched_plan_order_state_order_revision",
            "injection_scheduling_demand_order_versions",
            ["order_revision_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_injection_scheduling_plan_order_states_order_revision_id",
            ["order_revision_id"],
        )
        batch_op.create_index(
            "ix_inj_sched_plan_order_state_readiness",
            ["factory_readiness_status"],
        )

    company_scope = sa.table(
        "injection_scheduling_company_scopes",
        sa.column("id", sa.String),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("legal_entity_id", sa.String),
        sa.column("status", sa.String),
        sa.column("revision", sa.Integer),
        sa.column("created_by", sa.String),
        sa.column("created_at", sa.String),
        sa.column("updated_at", sa.String),
    )
    memberships = sa.table(
        "injection_scheduling_company_factory_memberships",
        sa.column("id", sa.String),
        sa.column("company_scope_id", sa.String),
        sa.column("factory_id", sa.String),
        sa.column("status", sa.String),
        sa.column("revision", sa.Integer),
        sa.column("created_by", sa.String),
        sa.column("created_at", sa.String),
    )
    created_at = "2026-08-09T00:00:00+08:00"
    op.bulk_insert(
        company_scope,
        [
            {
                "id": "company:royal-regent",
                "code": "ROYAL_REGENT",
                "name": "Royal Regent",
                "legal_entity_id": "",
                "status": "ACTIVE",
                "revision": 1,
                "created_by": "system:migration",
                "created_at": created_at,
                "updated_at": created_at,
            }
        ],
    )
    op.bulk_insert(
        memberships,
        [
            {
                "id": f"company:royal-regent:{factory_id}",
                "company_scope_id": "company:royal-regent",
                "factory_id": factory_id,
                "status": "ACTIVE",
                "revision": 1,
                "created_by": "system:migration",
                "created_at": created_at,
            }
            for factory_id in (
                "huakang-a",
                "huakang-b",
                "huakang-c",
                "huakang-d",
                "huadeng",
                "huaxing",
            )
        ],
    )


def downgrade() -> None:
    with op.batch_alter_table("injection_scheduling_plan_order_states") as batch_op:
        batch_op.drop_index(
            "ix_inj_sched_plan_order_state_readiness"
        )
        batch_op.drop_index(
            "ix_injection_scheduling_plan_order_states_order_revision_id"
        )
        batch_op.drop_constraint(
            "fk_inj_sched_plan_order_state_order_revision",
            type_="foreignkey",
        )
        batch_op.drop_column("factory_readiness_status")
        batch_op.drop_column("order_revision_id")

    with op.batch_alter_table("injection_scheduling_tasks") as batch_op:
        batch_op.drop_index("ix_injection_scheduling_tasks_physical_mold_asset_id")
        batch_op.drop_constraint(
            "fk_inj_sched_task_physical_mold_asset",
            type_="foreignkey",
        )
        batch_op.drop_column("physical_mold_asset_id")

    with op.batch_alter_table("injection_scheduling_molds") as batch_op:
        batch_op.drop_index("ix_injection_scheduling_molds_definition_id")
        batch_op.drop_constraint(
            "fk_inj_sched_mold_shared_definition",
            type_="foreignkey",
        )
        batch_op.drop_column("definition_id")

    for table_name in (
        "injection_scheduling_mold_reservations",
        "injection_scheduling_mold_asset_movements",
        "injection_scheduling_legacy_mold_copy_bindings",
        "injection_scheduling_factory_mold_capabilities",
        "injection_scheduling_demand_resolution_snapshots",
        "injection_scheduling_demand_order_versions",
        "injection_scheduling_commercial_rate_rules",
        "injection_scheduling_physical_mold_assets",
        "injection_scheduling_mold_output_specs",
        "injection_scheduling_mold_aliases",
        "injection_scheduling_customer_aliases",
        "injection_scheduling_field_evidence",
        "injection_scheduling_demand_import_rows",
        "injection_scheduling_customer_identities",
        "injection_scheduling_mold_definitions",
        "injection_scheduling_company_factory_memberships",
        "injection_scheduling_master_data_proposals",
        "injection_scheduling_demand_order_identities",
        "injection_scheduling_company_scopes",
    ):
        op.drop_table(table_name)

    with op.batch_alter_table("injection_scheduling_import_batches") as batch_op:
        batch_op.drop_index("ix_injection_scheduling_import_batches_resolution_digest")
        batch_op.drop_index("ix_injection_scheduling_import_batches_document_kind")
        batch_op.drop_constraint(
            "ck_injection_scheduling_import_batch_status",
            type_="check",
        )
        batch_op.drop_column("artifact_rebind_count")
        batch_op.drop_column("partial_confirmation_json")
        batch_op.drop_column("ui_state_json")
        batch_op.drop_column("mapping_draft_json")
        batch_op.drop_column("resolution_digest")
        batch_op.drop_column("source_namespace_id")
        batch_op.drop_column("document_kind")
        batch_op.create_check_constraint(
            "ck_injection_scheduling_import_batch_status",
            "status IN ('PREVIEW', 'CONFIRMED')",
        )

    with op.batch_alter_table("injection_scheduling_import_profiles") as batch_op:
        batch_op.drop_index("ix_injection_scheduling_import_profiles_document_kind")
        batch_op.drop_column("recognition_json")
        batch_op.drop_column("source_namespace_id")
        batch_op.drop_column("document_kind")
