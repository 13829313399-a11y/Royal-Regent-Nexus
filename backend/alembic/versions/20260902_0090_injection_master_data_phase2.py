"""Extend the retained injection masters for Phase 2.

Revision ID: 20260902_0090
Revises: 20260901_0089
"""

import re
import unicodedata
from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic.util.exc import CommandError

from alembic import op

revision: str = "20260902_0090"
down_revision: str | Sequence[str] | None = "20260901_0089"
branch_labels = None
depends_on = None

FACTORIES = "factory_id IN ('huaxing', 'huadeng', 'huakang-a', 'huakang-b')"
MACHINE_COLUMNS = (
    ("normalized_code", sa.String(128), ""),
    ("machine_a_tier", sa.Numeric(12, 3), None),
    ("clamping_force_tons", sa.Numeric(18, 6), None),
    ("platen_x_mm", sa.Numeric(18, 6), None),
    ("platen_y_mm", sa.Numeric(18, 6), None),
    ("machine_type", sa.String(32), "STANDARD"),
    ("asset_no", sa.String(128), ""),
    ("manufacturer", sa.String(128), ""),
    ("model", sa.String(128), ""),
    ("manufactured_date", sa.String(10), ""),
    ("screw_details", sa.String(255), ""),
    ("source_reference", sa.String(255), ""),
)
MOLD_COLUMNS = (
    ("normalized_code", sa.String(128), ""),
    ("required_machine_a", sa.Numeric(12, 3), None),
    ("required_machine_a_reason", sa.String(255), ""),
    ("mold_family_code", sa.String(128), ""),
    ("standard_cycle_seconds", sa.Numeric(18, 6), None),
    ("required_machine_type", sa.String(32), "STANDARD"),
    ("source_reference", sa.String(255), ""),
)
SIDECARS = (
    "injection_schedule_mold_aliases",
    "injection_schedule_mold_factory_profiles",
    "injection_schedule_machine_aliases",
    "injection_schedule_machine_status_events",
)


def _tracking_columns() -> list[sa.Column]:
    return [
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    ]


def upgrade() -> None:
    op.add_column(
        "injection_schedule_machine_unavailable_windows",
        sa.Column(
            "is_cancelled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    for table, columns in (
        ("injection_schedule_machines", MACHINE_COLUMNS),
        ("injection_schedule_molds", MOLD_COLUMNS),
    ):
        for name, kind, default in columns:
            op.add_column(
                table,
                sa.Column(
                    name,
                    kind,
                    nullable=default is None,
                    server_default=default,
                ),
            )

    # A is an explicit business tier, never inferred from physical tons/OZ.
    connection = op.get_bind()
    for table, code in (
        ("injection_schedule_machines", "machine_code"),
        ("injection_schedule_molds", "mold_code"),
    ):
        for row in connection.execute(
            sa.text(f"SELECT id, {code} AS code FROM {table}")
        ).mappings():
            normalized = "".join(
                unicodedata.normalize("NFKC", row["code"]).upper().split()
            )
            connection.execute(
                sa.text(f"UPDATE {table} SET normalized_code = :code WHERE id = :id"),
                {"code": normalized, "id": row["id"]},
            )
    op.create_index(
        "ix_inj_machine_normalized",
        "injection_schedule_machines",
        ["factory_id", "normalized_code"],
    )
    op.create_index(
        "ix_inj_mold_normalized", "injection_schedule_molds", ["normalized_code"]
    )
    for table, label, target in (
        ("injection_schedule_machines", "machine_a_label", "machine_a_tier"),
        ("injection_schedule_molds", "required_machine_a_label", "required_machine_a"),
    ):
        for row in connection.execute(
            sa.text(f"SELECT id, {label} AS label FROM {table}")
        ).mappings():
            label_text = unicodedata.normalize("NFKC", row["label"])
            match = re.match(r"\s*(\d+(?:\.\d+)?)\s*[Aa](?![A-Za-z])", label_text)
            tiers = re.findall(r"\d+(?:\.\d+)?\s*[Aa]", label_text)
            if match and len(tiers) == 1 and Decimal(match[1]) > 0:
                connection.execute(
                    sa.text(f"UPDATE {table} SET {target} = :tier WHERE id = :id"),
                    {"tier": str(Decimal(match[1])), "id": row["id"]},
                )

    with op.batch_alter_table("injection_schedule_machines") as batch:
        batch.drop_constraint("ck_injection_schedule_machine_status", type_="check")
        batch.create_check_constraint(
            "ck_injection_schedule_machine_status",
            (
                "status IN ('AVAILABLE', 'RUNNING', 'CHANGEOVER', 'MAINTENANCE', "
                "'FAULT', 'DISABLED')"
            ),
        )
        batch.create_check_constraint(
            "ck_injection_machine_explicit_a",
            ("machine_a_tier IS NULL OR machine_a_tier > 0"),
        )
    with op.batch_alter_table("injection_schedule_molds") as batch:
        batch.create_check_constraint(
            "ck_injection_mold_explicit_a",
            ("required_machine_a IS NULL OR required_machine_a > 0"),
        )

    op.create_table(
        SIDECARS[0],
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("mold_id", sa.String(96), nullable=False),
        sa.Column("alias_code", sa.String(128), nullable=False),
        sa.Column("normalized_alias", sa.String(128), nullable=False),
        sa.Column("alias_type", sa.String(32), nullable=False, server_default="LEGACY"),
        sa.Column("source_factory_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("valid_from", sa.String(40), nullable=False),
        sa.Column("valid_to", sa.String(40), nullable=True),
        *_tracking_columns(),
        sa.ForeignKeyConstraint(["mold_id"], ["injection_schedule_molds.id"]),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'RETIRED')", name="ck_inj_mold_alias_status"
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from < valid_to", name="ck_inj_mold_alias_dates"
        ),
    )
    op.create_index(
        "uq_inj_mold_alias_active",
        SIDECARS[0],
        ["normalized_alias"],
        unique=True,
        sqlite_where=sa.text("status = 'ACTIVE'"),
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index("ix_inj_mold_alias_mold", SIDECARS[0], ["mold_id"])

    op.create_table(
        SIDECARS[1],
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("mold_id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column(
            "is_present", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "status", sa.String(24), nullable=False, server_default="UNAVAILABLE"
        ),
        sa.Column("location", sa.String(255), nullable=False, server_default=""),
        sa.Column("required_machine_a_override", sa.Numeric(12, 3), nullable=True),
        sa.Column("override_reason", sa.String(500), nullable=False, server_default=""),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        *_tracking_columns(),
        sa.ForeignKeyConstraint(["mold_id"], ["injection_schedule_molds.id"]),
        sa.UniqueConstraint(
            "mold_id", "factory_id", name="uq_inj_mold_profile_factory"
        ),
        sa.CheckConstraint(FACTORIES, name="ck_inj_mold_profile_factory"),
        sa.CheckConstraint(
            "status IN ('AVAILABLE', 'MAINTENANCE', 'UNAVAILABLE')",
            name="ck_inj_mold_profile_status",
        ),
        sa.CheckConstraint(
            "required_machine_a_override IS NULL OR required_machine_a_override > 0",
            name="ck_inj_mold_profile_a",
        ),
    )
    op.create_index(
        "ix_inj_mold_profile_factory_status", SIDECARS[1], ["factory_id", "status"]
    )

    op.create_table(
        SIDECARS[2],
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("machine_id", sa.String(96), nullable=False),
        sa.Column("alias_code", sa.String(128), nullable=False),
        sa.Column("normalized_alias", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("valid_from", sa.String(40), nullable=False),
        sa.Column("valid_to", sa.String(40), nullable=True),
        *_tracking_columns(),
        sa.ForeignKeyConstraint(
            ["machine_id", "factory_id"],
            [
                "injection_schedule_machines.id",
                "injection_schedule_machines.factory_id",
            ],
        ),
        sa.CheckConstraint(FACTORIES, name="ck_inj_machine_alias_factory"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'RETIRED')", name="ck_inj_machine_alias_status"
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from < valid_to",
            name="ck_inj_machine_alias_dates",
        ),
    )
    op.create_index(
        "uq_inj_machine_alias_active",
        SIDECARS[2],
        ["factory_id", "normalized_alias"],
        unique=True,
        sqlite_where=sa.text("status = 'ACTIVE'"),
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "ix_inj_machine_alias_machine", SIDECARS[2], ["machine_id", "factory_id"]
    )

    op.create_table(
        SIDECARS[3],
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("machine_id", sa.String(96), nullable=False),
        sa.Column("previous_status", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("effective_at", sa.String(40), nullable=False),
        sa.Column("expected_restore_at", sa.String(40), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(
            ["machine_id", "factory_id"],
            [
                "injection_schedule_machines.id",
                "injection_schedule_machines.factory_id",
            ],
        ),
        sa.CheckConstraint(FACTORIES, name="ck_inj_machine_event_factory"),
        sa.CheckConstraint(
            "status IN ('AVAILABLE', 'RUNNING', 'CHANGEOVER', 'MAINTENANCE', 'FAULT', 'DISABLED')",
            name="ck_inj_machine_event_status",
        ),
    )
    op.create_index(
        "ix_inj_machine_event_history",
        SIDECARS[3],
        ["factory_id", "machine_id", "effective_at"],
    )


def downgrade() -> None:
    raise CommandError(
        "0090 preserves master/alias/state evidence; restore a verified pre-0090 "
        "backup instead of dropping Phase 2 data"
    )
