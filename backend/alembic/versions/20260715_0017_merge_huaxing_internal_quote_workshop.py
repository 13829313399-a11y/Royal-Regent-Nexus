"""merge Huaxing internal quote workshops

Revision ID: 20260715_0017
Revises: 20260715_0016
Create Date: 2026-07-15 21:00:00
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "20260715_0017"
down_revision: Union[str, None] = "20260715_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _collision_version(original: str, sequence: int) -> str:
    suffix = f"-合并{sequence}"
    return f"{original[:64 - len(suffix)]}{suffix}"


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute(sa.text("""
            DO $$
            DECLARE
                row_record RECORD;
                candidate VARCHAR(64);
                sequence_number INTEGER;
            BEGIN
                FOR row_record IN
                    SELECT id, quote_no, version_label
                    FROM internal_quotes
                    WHERE factory_id = 'huaxing'
                      AND workshop_code IN ('new-workshop', 'old-workshop')
                    ORDER BY created_at, id
                LOOP
                    candidate := row_record.version_label;
                    sequence_number := 2;
                    WHILE EXISTS (
                        SELECT 1
                        FROM internal_quotes
                        WHERE factory_id = 'huaxing'
                          AND workshop_code = 'huaxing-workshop'
                          AND quote_no = row_record.quote_no
                          AND version_label = candidate
                    ) LOOP
                        candidate := LEFT(
                            row_record.version_label,
                            64 - CHAR_LENGTH('-合并' || sequence_number::TEXT)
                        ) || '-合并' || sequence_number::TEXT;
                        sequence_number := sequence_number + 1;
                    END LOOP;
                    UPDATE internal_quotes
                    SET workshop_code = 'huaxing-workshop',
                        workshop_name = '华兴',
                        version_label = candidate
                    WHERE id = row_record.id;
                END LOOP;
            END $$;
        """))
        return

    connection = op.get_bind()
    rows = connection.execute(sa.text("""
        SELECT id, workshop_code, quote_no, version_label
        FROM internal_quotes
        WHERE factory_id = 'huaxing'
        ORDER BY created_at, id
    """)).mappings().all()

    occupied = {
        (row["quote_no"], row["version_label"])
        for row in rows
        if row["workshop_code"] == "huaxing-workshop"
    }
    for row in rows:
        if row["workshop_code"] not in {"new-workshop", "old-workshop"}:
            continue
        version_label = row["version_label"]
        sequence = 2
        while (row["quote_no"], version_label) in occupied:
            version_label = _collision_version(row["version_label"], sequence)
            sequence += 1
        connection.execute(
            sa.text("""
                UPDATE internal_quotes
                SET workshop_code = 'huaxing-workshop',
                    workshop_name = '华兴',
                    version_label = :version_label
                WHERE id = :quote_id
            """),
            {"quote_id": row["id"], "version_label": version_label},
        )
        occupied.add((row["quote_no"], version_label))


def downgrade() -> None:
    op.execute(sa.text("""
        UPDATE internal_quotes
        SET workshop_code = 'new-workshop', workshop_name = '新车间'
        WHERE factory_id = 'huaxing' AND workshop_code = 'huaxing-workshop'
    """))
