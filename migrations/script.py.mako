"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | T}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = '${up_revision}'
down_revision: Union[str, None] = ${down_revision | T}
branch_labels: Union[str, Sequence[str], None] = ${branch_labels | T}
depends_on: Union[str, Sequence[str], None] = ${depends_on | T}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
