"""Add provider metadata to ai_decisions"""
revision = "150f429d1db6"
down_revision = "0001_initial_schema"
branch_labels = None
depend_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        "ai_decisions",
        sa.Column(
            "provider",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'openai'"),
        ),
    )
    op.add_column(
        "ai_decisions",
        sa.Column(
            "model_name",
            sa.String(length=255),
            nullable=True,
            server_default=sa.text("'gpt-4'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_decisions", "model_name")
    op.drop_column("ai_decisions", "provider")
