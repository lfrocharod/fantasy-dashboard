"""xG name-match coverage — a run-over-run record of which CL players got an
underlying-stat row and which didn't, so a missed star is visible (in the log
and on the Settings page) instead of silently getting no xGI.

Resolve a miss by adding a `player_id_overrides` row: `note = "<source name>|<source team>"`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# reasons a player ends up without a stat row
NO_NAME_MATCH = "no_name_match"   # name isn't in the source's squad index
NO_STAT_ROW = "no_stat_row"       # matched a player, but no season row for them
LOW_MINUTES = "low_minutes"       # matched + row, but too few minutes to trust
BELOW_MIN_PRICE = "below_min_price"  # deliberately skipped (cheap fringe player)

# a "notable" miss worth calling out in the one-line summary
NOTABLE_PRICE = 6.0


@dataclass(slots=True)
class XgCoverage:
    source: str
    total: int = 0
    matched: int = 0
    unmatched: list[dict] = field(default_factory=list)  # {id,name,team,price,reason}

    def hit(self) -> None:
        self.matched += 1

    def miss(self, pid: int, name: str, team: str, price: float, reason: str) -> None:
        self.unmatched.append({
            "id": pid, "name": name, "team": team,
            "price": round(float(price or 0.0), 1), "reason": reason,
        })

    def by_reason(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for u in self.unmatched:
            out[u["reason"]] = out.get(u["reason"], 0) + 1
        return out

    def notable(self) -> list[dict]:
        """Unmatched players expensive enough that a manager would notice, worst
        first — these are the ones to add an override for."""
        return sorted(
            (u for u in self.unmatched
             if u["price"] >= NOTABLE_PRICE and u["reason"] != BELOW_MIN_PRICE),
            key=lambda u: -u["price"],
        )

    def as_dict(self, top: int = 60) -> dict:
        ranked = sorted(self.unmatched, key=lambda u: -u["price"])
        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "source": self.source,
            "total": self.total,
            "matched": self.matched,
            "unmatched": len(self.unmatched),
            "byReason": self.by_reason(),
            "notableMissing": self.notable()[:top],
            "topMissing": ranked[:top],
        }

    def summary_line(self) -> str:
        notable = self.notable()[:8]
        tail = (
            "; notable misses: "
            + ", ".join(f"{u['name']} ({u['team']}, {u['price']})" for u in notable)
        ) if notable else ""
        return (
            f"xG coverage [{self.source}]: {self.matched}/{self.total} matched, "
            f"{len(self.unmatched)} without a stat row{tail}"
        )
