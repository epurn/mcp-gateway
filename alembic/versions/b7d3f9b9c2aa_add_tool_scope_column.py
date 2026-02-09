"""add tool scope column

Revision ID: b7d3f9b9c2aa
Revises: a1b2c3d4e5f6
Create Date: 2026-02-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7d3f9b9c2aa"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tool_scope_enum = sa.Enum("calculator", "git", "docs", name="tool_scope_enum")
    bind = op.get_bind()
    tool_scope_enum.create(bind, checkfirst=True)

    op.add_column(
        "tools",
        sa.Column(
            "scope",
            tool_scope_enum,
            nullable=True,
            comment="Endpoint scope for tool exposure and routing",
        ),
    )

    op.execute(
        """
        UPDATE tools
        SET scope = CASE
            WHEN name LIKE 'exact_%' THEN 'calculator'::tool_scope_enum
            WHEN name = 'document_generate' THEN 'docs'::tool_scope_enum
            WHEN name LIKE 'git_%' THEN 'git'::tool_scope_enum
            ELSE 'calculator'::tool_scope_enum
        END
        """
    )
    op.alter_column("tools", "scope", nullable=False)


def downgrade() -> None:
    op.drop_column("tools", "scope")
    op.execute("DROP TYPE IF EXISTS tool_scope_enum")
