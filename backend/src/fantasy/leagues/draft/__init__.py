"""Draft assistant ingestion. Sport-agnostic core, per-sport adapters.

NFL (ESPN + FantasyPros) is implemented. NBA and FPL adapters are stubs for
next season — same shape: produce a list of DraftRow and let nfl.py's merge/VBD
logic (generalised) write them.
"""

SPORTS = ("nfl", "nba", "fpl")
