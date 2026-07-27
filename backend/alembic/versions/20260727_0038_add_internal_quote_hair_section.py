"""add standalone internal quote hair section

Revision ID: 20260727_0038
Revises: 20260727_0037
Create Date: 2026-07-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260727_0038"
down_revision: str | Sequence[str] | None = "20260727_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    quotes = connection.execute(
        sa.text(
            """
            SELECT
                id,
                factory_id,
                formula_version,
                reference_snapshot_id,
                created_by,
                created_by_name,
                created_at,
                updated_at
            FROM internal_quotes
            ORDER BY id
            """
        )
    ).mappings()
    for quote in quotes:
        quote_id = str(quote["id"])
        exists = connection.execute(
            sa.text(
                """
                SELECT 1
                FROM internal_quote_sections
                WHERE quote_id = :quote_id AND department = 'hair'
                """
            ),
            {"quote_id": quote_id},
        ).first()
        if exists is not None:
            continue

        section_id = f"{quote_id}-hair"
        formula_version = str(quote["formula_version"] or "")
        reference_snapshot_id = str(quote["reference_snapshot_id"] or "")
        timestamp = str(quote["updated_at"] or quote["created_at"] or "")
        connection.execute(
            sa.text(
                """
                INSERT INTO internal_quote_sections (
                    id,
                    quote_id,
                    department,
                    department_name,
                    status,
                    payload_json,
                    calculation_json,
                    calculation_status,
                    calculation_hash,
                    calculation_formula_version,
                    calculation_reference_snapshot_id,
                    calculated_at,
                    dependency_hash,
                    dependency_status,
                    revision,
                    is_required,
                    filled_by,
                    filled_at,
                    submitted_by,
                    submitted_by_id,
                    submitted_at,
                    reviewed_by,
                    reviewed_at,
                    review_comment,
                    updated_at
                ) VALUES (
                    :id,
                    :quote_id,
                    'hair',
                    '车发部',
                    'draft',
                    '{}',
                    '{}',
                    'pending',
                    '',
                    :formula_version,
                    :reference_snapshot_id,
                    '',
                    '',
                    'current',
                    1,
                    :is_required,
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    :updated_at
                )
                """
            ),
            {
                "id": section_id,
                "quote_id": quote_id,
                "formula_version": formula_version,
                "reference_snapshot_id": reference_snapshot_id,
                "is_required": False,
                "updated_at": timestamp,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO internal_quote_section_revisions (
                    id,
                    quote_id,
                    section_id,
                    factory_id,
                    department,
                    revision,
                    status,
                    payload_json,
                    calculation_json,
                    formula_version,
                    input_hash,
                    reference_snapshot_id,
                    dependency_hash,
                    warnings_json,
                    reason,
                    created_by,
                    created_by_name,
                    created_at
                ) VALUES (
                    :id,
                    :quote_id,
                    :section_id,
                    :factory_id,
                    'hair',
                    1,
                    'draft',
                    '{}',
                    '{}',
                    :formula_version,
                    '',
                    :reference_snapshot_id,
                    '',
                    '[]',
                    'initial_hair_section_migration',
                    :created_by,
                    :created_by_name,
                    :created_at
                )
                """
            ),
            {
                "id": f"IQR-H-{quote_id}",
                "quote_id": quote_id,
                "section_id": section_id,
                "factory_id": str(quote["factory_id"] or ""),
                "formula_version": formula_version,
                "reference_snapshot_id": reference_snapshot_id,
                "created_by": str(quote["created_by"] or ""),
                "created_by_name": str(quote["created_by_name"] or ""),
                "created_at": timestamp,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    changed = connection.execute(
        sa.text(
            """
            SELECT quote_id
            FROM internal_quote_sections
            WHERE department = 'hair'
              AND EXISTS (
                SELECT 1
                FROM internal_quote_section_revisions migrated_revision
                WHERE migrated_revision.section_id = internal_quote_sections.id
                  AND migrated_revision.reason = 'initial_hair_section_migration'
              )
              AND (
                is_required = :is_required
                OR status <> 'draft'
                OR revision <> 1
                OR payload_json <> '{}'
                OR calculation_json <> '{}'
                OR calculation_status <> 'pending'
              )
            LIMIT 1
            """
        ),
        {"is_required": True},
    ).first()
    if changed is not None:
        raise RuntimeError(
            "20260727_0038 cannot remove a standalone hair section after it has "
            "participated in or stored data for an internal quote."
        )
    migrated_section_ids = [
        str(row[0])
        for row in connection.execute(
            sa.text(
                """
                SELECT DISTINCT section_id
                FROM internal_quote_section_revisions
                WHERE department = 'hair'
                  AND reason = 'initial_hair_section_migration'
                ORDER BY section_id
                """
            )
        )
    ]
    for section_id in migrated_section_ids:
        connection.execute(
            sa.text(
                """
                DELETE FROM internal_quote_section_revisions
                WHERE section_id = :section_id
                """
            ),
            {"section_id": section_id},
        )
        connection.execute(
            sa.text(
                """
                DELETE FROM internal_quote_sections
                WHERE id = :section_id AND department = 'hair'
                """
            ),
            {"section_id": section_id},
        )
