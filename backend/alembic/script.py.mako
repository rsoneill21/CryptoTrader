"""${message}"""
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depend_on = ${repr(depends_on)}

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    """Apply upgrade migrations."""
${upgrades if upgrades else "    pass"}


def downgrade() -> None:
    """Reverse upgrade migrations."""
${downgrades if downgrades else "    pass"}
