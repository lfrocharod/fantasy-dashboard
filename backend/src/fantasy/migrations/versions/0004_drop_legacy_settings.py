"""drop the league-state keys 0002 copied out of `settings`

Revision ID: 0004_drop_legacy_settings
Revises: 0003_model_predictions
Create Date: 2026-10-11

0002 copied league state out of `settings` into real tables and documents,
and left the keys behind so the previous app kept working through the
cutover (expand/contract). That app is gone and nothing reads them now: this
is the contract half. Configuration keys (league ids, cookies, team ids) stay.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_drop_legacy_settings"
down_revision: str | None = "0003_model_predictions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_KEYS = (
    # → documents
    "model.optimizer_output", "model.live_state", "model.live_rivals",
    "ingest.calibration", "ingest.xg_coverage", "draft.fpl.live",
    # → leagues, league_entries, matchups, my_lineup
    "ucl.current_matchday", "ucl.deadline_iso",
    "draft.fpl.mode", "draft.fpl.standings", "draft.fpl.schedule", "draft.fpl.my_lineup",
    "draft.fpl.my_squad",
    "draft.nfl.week", "draft.nfl.reg_weeks", "draft.nfl.playoff_weeks", "draft.nfl.playoff_teams",
    "draft.nfl.seeding_rule", "draft.nfl.slots", "draft.nfl.standings", "draft.nfl.schedule",
    "draft.nfl.my_roster",
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM settings WHERE key = ANY(:keys)"), {"keys": list(LEGACY_KEYS)}
    )


def downgrade() -> None:
    # Nothing to restore: the values live on in the tables 0002 filled.
    pass
