"""Settings pages (UCL connection + FPL/NFL league setup) and the NFL draft
board's pick tracker."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from fantasy.api.schemas import home as S
from fantasy.api.schemas.ucl import XgCoverage
from fantasy.config import Docs, Keys
from fantasy.core import models as M
from fantasy.core.secretbox import encrypt
from fantasy.core.store import get_document, get_settings, set_setting
from fantasy.leagues.draft.types import DEFAULT_ROSTER, FPL_ROSTER


def ucl_settings(session: Session) -> S.UclSettings:
    s = get_settings(session, [
        Keys.LEAGUE_ID, Keys.LEAGUE_CODE, Keys.ENTRY_ID, Keys.MATCHDAY_OVERRIDE,
        Keys.UEFA_AUTH_STATE, Keys.UEFA_TOKEN_SAVED_AT, Keys.MODEL_PARAMS,
    ])
    league = session.get(M.League, "ucl")
    cov = get_document(session, Docs.UCL_XG_COVERAGE)
    return S.UclSettings(
        league_id=s.get(Keys.LEAGUE_ID, ""),
        league_code=s.get(Keys.LEAGUE_CODE, ""),
        entry_id=s.get(Keys.ENTRY_ID, ""),
        matchday_override=s.get(Keys.MATCHDAY_OVERRIDE, ""),
        deadline_iso=league.deadline.isoformat() if league and league.deadline else "",
        auth_state=s.get(Keys.UEFA_AUTH_STATE, "unknown"),
        token_saved_at=s.get(Keys.UEFA_TOKEN_SAVED_AT) or None,
        has_token=bool(s.get(Keys.UEFA_TOKEN_SAVED_AT)),
        model_params=s.get(Keys.MODEL_PARAMS, ""),
        xg_coverage=XgCoverage.model_validate(cov) if cov else None,
    )


def update_ucl_settings(session: Session, body: S.UclSettingsUpdate) -> None:
    if body.league_id is not None:
        set_setting(session, Keys.LEAGUE_ID, body.league_id.strip())
    if body.league_code is not None:
        set_setting(session, Keys.LEAGUE_CODE, body.league_code.strip().upper())
    if body.entry_id is not None:
        set_setting(session, Keys.ENTRY_ID, body.entry_id.strip())
    if body.matchday_override is not None:
        set_setting(session, Keys.MATCHDAY_OVERRIDE,
                    str(body.matchday_override) if body.matchday_override else "")
    if body.model_params is not None:
        if body.model_params.strip():
            json.loads(body.model_params)  # reject malformed JSON (ValueError -> 400)
        set_setting(session, Keys.MODEL_PARAMS, body.model_params)
    if body.uefa_token:
        set_setting(session, Keys.UEFA_TOKEN, encrypt(body.uefa_token.strip()))
        set_setting(session, Keys.UEFA_TOKEN_SAVED_AT, datetime.now(UTC).isoformat())
        # the next sync verifies it and sets "authed" / "public_only"
        set_setting(session, Keys.UEFA_AUTH_STATE, "unverified")
    session.commit()


def draft_config(session: Session, sport: str) -> S.DraftConfig:
    p = f"draft.{sport}."
    s = get_settings(session, [p + k for k in (
        "league_id", "my_team_id", "my_slot", "teams", "scoring", "year", "espn_s2", "swid",
        "roster", "entry_id", "pl_profile",
    )])
    return S.DraftConfig(
        sport=sport,  # type: ignore[arg-type]
        league_id=s.get(p + "league_id", ""),
        my_team_id=s.get(p + "my_team_id", ""),
        my_slot=s.get(p + "my_slot", ""),
        teams=s.get(p + "teams", "12"),
        scoring=s.get(p + "scoring", "ppr"),
        year=s.get(p + "year", "2026"),
        roster=s.get(p + "roster", ""),
        entry_id=s.get(p + "entry_id", ""),
        has_cookies=bool(s.get(p + "pl_profile")) if sport == "fpl"
        else bool(s.get(p + "espn_s2") and s.get(p + "swid")),
    )


def update_draft_config(session: Session, b: S.DraftConfigUpdate) -> None:
    p = f"draft.{b.sport}."
    plain = {
        "league_id": b.league_id.strip() if b.league_id is not None else None,
        "my_team_id": str(b.my_team_id) if b.my_team_id is not None else None,
        "my_slot": str(b.my_slot) if b.my_slot is not None else None,
        "teams": str(b.teams) if b.teams is not None else None,
        "scoring": b.scoring,
        "year": str(b.year) if b.year is not None else None,
        "entry_id": b.entry_id.strip() if b.entry_id is not None else None,
    }
    for k, v in plain.items():
        if v is not None:
            set_setting(session, p + k, v)
    for k, v in (("espn_s2", b.espn_s2), ("swid", b.swid), ("pl_profile", b.pl_profile)):
        if v:
            set_setting(session, p + k, encrypt(v.strip()))
    session.commit()


# ---- draft board -----------------------------------------------------------------------


def board(session: Session, sport: str) -> S.DraftBoard:
    players = session.scalars(select(M.DraftPlayer).where(M.DraftPlayer.sport == sport)).all()
    picks = session.scalars(
        select(M.DraftPick).where(M.DraftPick.sport == sport).order_by(M.DraftPick.overall)
    ).all()
    s = get_settings(session, [f"draft.{sport}.teams", f"draft.{sport}.my_slot", f"draft.{sport}.roster"])
    roster = dict(FPL_ROSTER if sport == "fpl" else DEFAULT_ROSTER)
    try:
        if s.get(f"draft.{sport}.roster"):
            roster = json.loads(s[f"draft.{sport}.roster"])
    except ValueError:
        pass
    teams_raw = s.get(f"draft.{sport}.teams", "")
    slot_raw = s.get(f"draft.{sport}.my_slot", "")
    return S.DraftBoard(
        sport=sport,  # type: ignore[arg-type]
        players=[S.BoardPlayer.model_validate(p) for p in players],
        picks=[S.BoardPick.model_validate(p) for p in picks],
        teams=int(teams_raw) if teams_raw.isdigit() else (8 if sport == "fpl" else 12),
        my_slot=int(slot_raw) if slot_raw.isdigit() else None,
        roster=roster,
    )


def add_pick(session: Session, body: S.PickRequest) -> int:
    nxt = (session.scalar(
        select(func.max(M.DraftPick.overall)).where(M.DraftPick.sport == body.sport)
    ) or 0) + 1
    session.execute(
        insert(M.DraftPick)
        .values(
            sport=body.sport, overall=nxt, player_ext_id=body.ext_id, is_mine=body.is_mine,
            team_id=body.team_id or 0, team_name=body.team_name or ("Me" if body.is_mine else ""),
            source="manual",
        )
        .on_conflict_do_nothing()
    )
    session.commit()
    return nxt


def undo_pick(session: Session, sport: str, reset: bool) -> bool:
    if reset:
        session.execute(delete(M.DraftPick).where(M.DraftPick.sport == sport))
        session.commit()
        return True
    last = session.scalars(
        select(M.DraftPick)
        .where(M.DraftPick.sport == sport, M.DraftPick.source == "manual")
        .order_by(M.DraftPick.overall.desc())
        .limit(1)
    ).first()
    if last is None:
        return False
    session.delete(last)
    session.commit()
    return True
