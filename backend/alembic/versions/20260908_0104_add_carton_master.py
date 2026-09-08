"""Carton master data, location lifecycle and workshop destination snapshots."""
import sqlalchemy as sa
from alembic import op
revision = "20260908_0104"
down_revision = "20260908_0103"
branch_labels = None
depends_on = None
PERMISSION_CODE = "carton_procurement:master_manage"
SUPERVISOR_ROLE_IDS = ("admin", "manager", "position_general_manager", "position_carton_manager", "position_carton_supervisor")

def upgrade():
    op.create_table("carton_master_records",
        sa.Column("id", sa.String(96), primary_key=True), sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False), sa.Column("identity", sa.String(64), nullable=False),
        sa.Column("customer_code", sa.String(64), nullable=False), sa.Column("code", sa.String(128), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("preferred", sa.Integer(), nullable=False), sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("maintained", sa.Integer(), nullable=False), sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("factory_id", "kind", "identity", name="uq_carton_master_identity"),
        sa.UniqueConstraint("id", "factory_id", name="uq_carton_master_factory"))
    op.create_index("ix_carton_master_records_factory_id", "carton_master_records", ["factory_id"])
    op.create_table("carton_master_sources",
        sa.Column("id", sa.String(96), primary_key=True), sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("record_id", sa.String(96), nullable=False), sa.Column("order_id", sa.String(96), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False), sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("factory_id", "record_id", "order_id", "signature", name="uq_carton_master_source"),
        sa.ForeignKeyConstraint(["record_id", "factory_id"], ["carton_master_records.id", "carton_master_records.factory_id"]))
    op.create_index("ix_carton_master_sources_factory_id", "carton_master_sources", ["factory_id"])
    op.create_index("ix_carton_master_sources_record_id", "carton_master_sources", ["record_id"])
    op.add_column("carton_locations", sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"))
    op.add_column("carton_locations", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("carton_inventory_movements", sa.Column("workshop_id", sa.String(96), nullable=False, server_default=""))
    op.add_column("carton_inventory_movements", sa.Column("workshop_name", sa.String(128), nullable=False, server_default=""))
    op.add_column("carton_orders", sa.Column("master_config_id", sa.String(96), nullable=False, server_default=""))
    op.add_column("carton_orders", sa.Column("master_config_revision", sa.Integer(), nullable=False, server_default="0"))
    connection = op.get_bind()
    permission_id = f"perm-{PERMISSION_CODE.replace(':', '-')}"
    connection.execute(
        sa.text(
            """
            INSERT INTO auth_permissions (id, code, name, description)
            SELECT
                CAST(:id AS VARCHAR(96)),
                CAST(:code AS VARCHAR(128)),
                CAST(:name AS VARCHAR(128)),
                CAST(:description AS TEXT)
            WHERE NOT EXISTS (
                SELECT 1 FROM auth_permissions
                WHERE code = CAST(:code AS VARCHAR(128))
            )
            """
        ),
        {
            "id": permission_id,
            "code": PERMISSION_CODE,
            "name": "高级维护纸箱基础资料",
            "description": "维护纸箱基础资料、交期规则与仓库授权，保留历史业务快照",
        },
    )
    for role_id in SUPERVISOR_ROLE_IDS:
        connection.execute(
            sa.text(
                """
                INSERT INTO auth_role_permissions (id, role_id, permission_id)
                SELECT
                    CAST(:id AS VARCHAR(128)),
                    CAST(:role_id AS VARCHAR(96)),
                    CAST(:permission_id AS VARCHAR(96))
                WHERE EXISTS (
                    SELECT 1 FROM auth_roles
                    WHERE id = CAST(:role_id AS VARCHAR(96))
                )
                AND NOT EXISTS (
                    SELECT 1 FROM auth_role_permissions
                    WHERE role_id = CAST(:role_id AS VARCHAR(96))
                      AND permission_id = CAST(:permission_id AS VARCHAR(96))
                )
                """
            ),
            {
                "id": f"{role_id}:{permission_id}",
                "role_id": role_id,
                "permission_id": permission_id,
            },
        )


def downgrade():
    raise RuntimeError("基础资料与领用去向已纳入审计，禁止自动删除；请使用经过验证的备份恢复流程")
