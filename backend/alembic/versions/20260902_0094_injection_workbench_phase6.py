"""Versioned workbench, immutable publication evidence and command receipts."""

import sqlalchemy as sa
from alembic import op
from alembic.util import CommandError

revision = "20260902_0094"
down_revision = "20260902_0093"
branch_labels = None
depends_on = None
TABLE = "injection_schedule_versions"
RECEIPTS = "injection_schedule_commands"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_id", sa.String(96), nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("document_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("published_json", sa.Text(), nullable=True),
        sa.Column("published_revision", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.String(40), nullable=True),
        sa.Column("published_by", sa.String(64), nullable=True),
        sa.Column("published_by_name", sa.String(128), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "factory_id", "revision", name="uq_is_version_factory_revision"
        ),
        sa.UniqueConstraint(
            "factory_id", "published_revision", name="uq_is_version_publication"
        ),
        sa.CheckConstraint(
            "version >= 1 AND revision >= 1", name="ck_is_version_positive"
        ),
        sa.CheckConstraint(
            "source_kind IN ('AUTO','SCHEDULE')", name="ck_is_version_source"
        ),
        sa.CheckConstraint(
            "(status = 'DRAFT' AND published_json IS NULL AND published_revision IS NULL) OR (status = 'PUBLISHED' AND published_json IS NOT NULL AND published_revision IS NOT NULL AND published_at IS NOT NULL AND published_by IS NOT NULL)",
            name="ck_is_version_publication",
        ),
    )
    op.create_index(
        "ix_is_version_factory_status", TABLE, ["factory_id", "status", "revision"]
    )
    op.create_table(
        RECEIPTS,
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("request_key", sa.String(96), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "factory_id", "request_key", name="uq_is_command_factory_key"
        ),
    )
    # Supersession is derived from the latest published revision, never by
    # updating an old snapshot. Draft deletion is also forbidden (audit history).
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            f"CREATE TRIGGER trg_is_version_no_update BEFORE UPDATE ON {TABLE} WHEN OLD.status='PUBLISHED' BEGIN SELECT RAISE(ABORT, 'Published schedules are immutable'); END"
        )
        op.execute(
            f"CREATE TRIGGER trg_is_version_no_delete BEFORE DELETE ON {TABLE} BEGIN SELECT RAISE(ABORT, 'Schedule history is immutable'); END"
        )
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER trg_is_command_no_{action.lower()} BEFORE {action} ON {RECEIPTS} BEGIN SELECT RAISE(ABORT, 'Command receipts are immutable'); END"
            )
    elif op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE FUNCTION reject_is_version_mutation_0094() RETURNS trigger AS $$ BEGIN IF TG_OP='DELETE' OR OLD.status='PUBLISHED' THEN RAISE EXCEPTION 'Schedule history is immutable'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql"
        )
        op.execute(
            f"CREATE TRIGGER trg_is_version_immutable BEFORE UPDATE OR DELETE ON {TABLE} FOR EACH ROW EXECUTE FUNCTION reject_is_version_mutation_0094()"
        )
        op.execute(
            "CREATE FUNCTION reject_is_command_mutation_0094() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Command receipts are immutable'; END; $$ LANGUAGE plpgsql"
        )
        op.execute(
            f"CREATE TRIGGER trg_is_command_immutable BEFORE UPDATE OR DELETE ON {RECEIPTS} FOR EACH ROW EXECUTE FUNCTION reject_is_command_mutation_0094()"
        )


def downgrade():
    raise CommandError("Phase 6 版本和发布审计不可删除；请恢复验证过的迁移前备份。")
