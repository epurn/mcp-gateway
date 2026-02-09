"""add audit endpoint path

Revision ID: d2a4c86f1e12
Revises: b7d3f9b9c2aa
Create Date: 2026-02-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2a4c86f1e12"
down_revision: Union[str, None] = "b7d3f9b9c2aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column(
            "endpoint_path",
            sa.String(length=255),
            nullable=True,
            comment="API endpoint path used for invocation",
        ),
    )
    op.execute("UPDATE audit_logs SET endpoint_path = '/unknown' WHERE endpoint_path IS NULL")
    op.alter_column("audit_logs", "endpoint_path", nullable=False)
    op.create_index(op.f("ix_audit_logs_endpoint_path"), "audit_logs", ["endpoint_path"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_logs_endpoint_path"), table_name="audit_logs")
    op.drop_column("audit_logs", "endpoint_path")
