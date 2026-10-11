"""model predictions: what each model said before a round, graded after it

Revision ID: 0003_model_predictions
Revises: 0002_league_state
Create Date: 2026-10-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_model_predictions"
down_revision: str | None = "0002_league_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_predictions",
        sa.Column("sport", sa.Text(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("ext_id", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("predicted", sa.REAL(), nullable=False),
        sa.Column("actual", sa.REAL(), nullable=True),
        sa.Column("made_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("sport", "round", "ext_id", "model", name="model_predictions_pkey"),
    )


def downgrade() -> None:
    op.drop_table("model_predictions")
