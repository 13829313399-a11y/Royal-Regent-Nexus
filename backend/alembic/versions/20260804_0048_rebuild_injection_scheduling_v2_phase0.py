"""rebuild injection scheduling V2 phase 0 backend

Revision ID: 20260804_0048
Revises: 20260804_0047
Create Date: 2026-08-04
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0048"
down_revision: str | Sequence[str] | None = "20260804_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PHASE2_FILE = "20260731_0043_rebuild_injection_scheduling_phase2_master_data.py"
_PHASE3_FILE = "20260731_0044_create_injection_scheduling_phase3_execution.py"
_PHASE4_FILE = "20260731_0045_create_injection_scheduling_phase4_import.py"

_TABLES_CHILD_FIRST = (
    "injection_scheduling_import_issues",
    "injection_scheduling_shift_reports",
    "injection_scheduling_published_snapshots",
    "injection_scheduling_plan_revisions",
    "injection_scheduling_audit_events",
    "injection_scheduling_tasks",
    "injection_scheduling_plans",
    "injection_scheduling_orders",
    "injection_scheduling_rule_sets",
    "injection_scheduling_molds",
    "injection_scheduling_machines",
    "injection_scheduling_import_batches",
)

_DEFAULT_RULE_CONFIG = {
    "schema_version": "phase0-v2",
    "arm_coverage": {
        "none": ["none"],
        "single": ["none", "single"],
        "dual": ["none", "single", "dual"],
        "multi": ["none", "single", "dual", "multi"],
    },
    "process_rule_codes": [
        "pvc_screw",
        "pc_screw",
        "transparent_only",
        "no_core_pull",
        "high_pressure_limit",
        "two_color",
        "vertical",
        "semi_auto",
    ],
    "scoring_weights": {
        "delivery_urgency": 30,
        "business_priority": 20,
        "same_mold": 18,
        "same_material_color": 12,
        "machine_fit": 10,
        "queue_balance": 10,
    },
    "color_scale": [],
    "notes": "V2 Phase 0：尺寸仅作工程资料，不参与机台资格判定。",
}


def _load_historical_migration(file_name: str, module_name: str) -> ModuleType:
    """Reuse immutable table/guard definitions from the immediately prior rebuild."""

    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load historical migration {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _add_v2_master_columns() -> None:
    op.add_column(
        "injection_scheduling_machines",
        sa.Column(
            "machine_class_raw", sa.String(128), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "injection_scheduling_machines",
        sa.Column("machine_a_class", sa.Numeric(8, 3), nullable=True),
    )
    op.add_column(
        "injection_scheduling_machines",
        sa.Column(
            "normalization_status",
            sa.String(32),
            nullable=False,
            server_default="REVIEW_REQUIRED",
        ),
    )
    op.add_column(
        "injection_scheduling_machines",
        sa.Column("process_tags_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "injection_scheduling_machines",
        sa.Column(
            "special_machine_type", sa.String(64), nullable=False, server_default=""
        ),
    )
    op.create_index(
        "ix_injection_scheduling_machines_machine_a_class",
        "injection_scheduling_machines",
        ["machine_a_class"],
    )
    op.create_index(
        "ix_injection_scheduling_machines_normalization_status",
        "injection_scheduling_machines",
        ["normalization_status"],
    )

    op.add_column(
        "injection_scheduling_molds",
        sa.Column("mold_class_raw", sa.String(128), nullable=False, server_default=""),
    )
    op.add_column(
        "injection_scheduling_molds",
        sa.Column("mold_a_class", sa.Numeric(8, 3), nullable=True),
    )
    op.add_column(
        "injection_scheduling_molds",
        sa.Column(
            "normalization_status",
            sa.String(32),
            nullable=False,
            server_default="REVIEW_REQUIRED",
        ),
    )
    op.add_column(
        "injection_scheduling_molds",
        sa.Column("process_tags_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "injection_scheduling_molds",
        sa.Column(
            "special_machine_type", sa.String(64), nullable=False, server_default=""
        ),
    )
    op.create_index(
        "ix_injection_scheduling_molds_mold_a_class",
        "injection_scheduling_molds",
        ["mold_a_class"],
    )
    op.create_index(
        "ix_injection_scheduling_molds_normalization_status",
        "injection_scheduling_molds",
        ["normalization_status"],
    )

    with op.batch_alter_table("injection_scheduling_machines") as batch_op:
        batch_op.create_check_constraint(
            "ck_injection_scheduling_machine_a_class",
            "machine_a_class IS NULL OR machine_a_class > 0",
        )
        batch_op.create_check_constraint(
            "ck_injection_scheduling_machine_normalization_status",
            "normalization_status IN ('COMPLETE', 'REVIEW_REQUIRED')",
        )
    with op.batch_alter_table("injection_scheduling_molds") as batch_op:
        batch_op.alter_column(
            "required_arm_type",
            existing_type=sa.String(64),
            server_default="",
        )
        batch_op.create_check_constraint(
            "ck_injection_scheduling_mold_a_class",
            "mold_a_class IS NULL OR mold_a_class > 0",
        )
        batch_op.create_check_constraint(
            "ck_injection_scheduling_mold_normalization_status",
            "normalization_status IN ('COMPLETE', 'REVIEW_REQUIRED')",
        )


def _replace_default_rule_config() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE injection_scheduling_rule_sets
            SET config_json = CAST(:config_json AS TEXT),
                allow_mold_rotation_90 = :allow_rotation
            WHERE id LIKE 'isrules-default-%'
            """
        ),
        {
            "config_json": json.dumps(
                _DEFAULT_RULE_CONFIG,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "allow_rotation": False,
        },
    )


def upgrade() -> None:
    phase2 = _load_historical_migration(_PHASE2_FILE, "injection_phase2_0043")
    phase3 = _load_historical_migration(_PHASE3_FILE, "injection_phase3_0044")
    phase4 = _load_historical_migration(_PHASE4_FILE, "injection_phase4_0045")

    phase2._create_tables()
    _add_v2_master_columns()
    phase2._seed_permissions()
    phase2._seed_default_rules()
    _replace_default_rule_config()
    phase3._create_orders()
    phase3._create_plans()
    phase3._create_tasks()
    phase3._create_reports_and_snapshots()
    phase3._create_audit_events()
    phase3._create_guards()
    phase4._create_import_batches()
    phase4._create_import_issues()
    phase4._extend_tasks()
    phase4._create_guards()


def downgrade() -> None:
    connection = op.get_bind()
    populated = {
        table_name: connection.execute(
            sa.text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar_one()
        for table_name in _TABLES_CHILD_FIRST
        if table_name != "injection_scheduling_rule_sets"
    }
    custom_rules = connection.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM injection_scheduling_rule_sets
            WHERE id NOT LIKE 'isrules-default-%'
            """
        )
    ).scalar_one()
    if any(populated.values()) or custom_rules:
        raise RuntimeError(
            "20260804_0048 cannot be downgraded after V2 injection scheduling "
            "data exists; back up the domain first."
        )

    phase2 = _load_historical_migration(_PHASE2_FILE, "injection_phase2_0043_down")
    phase3 = _load_historical_migration(_PHASE3_FILE, "injection_phase3_0044_down")
    phase4 = _load_historical_migration(_PHASE4_FILE, "injection_phase4_0045_down")
    phase4._drop_guards()
    phase3._drop_guards()
    phase2._remove_permissions()
    for table_name in _TABLES_CHILD_FIRST:
        op.drop_table(table_name)
