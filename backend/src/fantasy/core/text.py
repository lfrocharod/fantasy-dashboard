"""Name normalisation shared by every league's identity matching."""

from __future__ import annotations

import unicodedata


def normalise(s: str) -> str:
    """ASCII-fold, lowercase and collapse punctuation: "Kylian Mbappé-Lottin" ->
    "kylian mbappe lottin". Used to match player/team names across sources."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().replace(".", " ").replace("-", " ").split())
