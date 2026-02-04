"""add smart routing fields

Revision ID: a1b2c3d4e5f6
Revises: ffbe370a823f
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False
    Vector = None

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '6a9d296e9ddf'  # Changed from ffbe370a823f to fix migration chain
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add smart routing fields to tools table."""
    # Add pgvector extension
    if PGVECTOR_AVAILABLE:
        op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    
    # Add categories array
    op.add_column('tools', sa.Column(
        'categories',
        ARRAY(sa.String(50)),
        nullable=False,
        server_default='{}',
        comment='Tool categories for filtering'
    ))
    
    # Add embedding vector (1536 dimensions for OpenAI ada-002)
    if PGVECTOR_AVAILABLE and Vector:
        op.execute(
            'ALTER TABLE tools ADD COLUMN embedding vector(1536)'
        )
        op.execute(
            "COMMENT ON COLUMN tools.embedding IS 'Tool description embedding for RAG'"
        )
    
    # Add usage tracking
    op.add_column('tools', sa.Column(
        'usage_count',
        sa.Integer(),
        nullable=False,
        server_default='0',
        comment='Number of times tool has been invoked'
    ))
    
    op.add_column('tools', sa.Column(
        'last_used_at',
        sa.DateTime(timezone=True),
        nullable=True,
        comment='Last time tool was invoked'
    ))
    
    # Add input_schema JSON column for dynamic schemas
    op.add_column('tools', sa.Column(
        'input_schema',
        sa.JSON(),
        nullable=True,
        comment='JSON Schema for tool inputs'
    ))
    
    # Create indexes
    op.create_index(
        'idx_tools_categories',
        'tools',
        ['categories'],
        postgresql_using='gin'
    )
    
    if PGVECTOR_AVAILABLE:
        op.execute(
            'CREATE INDEX idx_tools_embedding ON tools '
            'USING ivfflat (embedding vector_cosine_ops) '
            'WITH (lists = 100)'
        )


def downgrade() -> None:
    """Remove smart routing fields."""
    # Drop indexes
    if PGVECTOR_AVAILABLE:
        op.execute('DROP INDEX IF EXISTS idx_tools_embedding')
    op.drop_index('idx_tools_categories', table_name='tools')
    
    # Drop columns
    op.drop_column('tools', 'input_schema')
    op.drop_column('tools', 'last_used_at')
    op.drop_column('tools', 'usage_count')
    if PGVECTOR_AVAILABLE:
        op.execute('ALTER TABLE tools DROP COLUMN IF EXISTS embedding')
    op.drop_column('tools', 'categories')
    
    # Note: We don't drop the vector extension as other tables might use it
