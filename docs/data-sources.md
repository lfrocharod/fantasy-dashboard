# Data sources

The app never trusts a single feed. Every decision input — will a player start,
is there an injury scare, how many points will they score — is a **blend** of
independent sources, merged by `fantasy/leagues/ucl/sources/blend.py`:

```python
from fantasy.leagues.ucl.sources.blend import Signal, compose

c = compose([
    Signal("sofascore_form",  0.88, confidence=0.7),
    Signal("uefa_minutes",    0.80, confidence=0.55),
    Signal("official_club",   0.30, confidence=0.85),   # presser: "late fitness test"
], prior=0.70, prior_weight=0.18, lo=0.05, hi=0.98)

c.value          # 0.61  -> the number the model uses
c.disagreement   # 0.41  -> sources conflict: treat as a rotation / fitness risk
c.why()          # "official_club 0.30, sofascore_form 0.88, ... · sources disagree"
```

`disagreement` is a first-class output: when a stats feed says "nailed" and the
club says "doubt", that gap **is** the signal a point estimate would hide.

---

## Wired today

| League | Source | Feeds | Access |
|---|---|---|---|
| **UCL** | UEFA UCL Fantasy feed | prices, ownership, availability (`pStatus`/`qStatus`), **minutes played** (→ `minutes_prior`), season points | public JSON |
| UCL | UEFA match centre (`match.uefa.com`) | **confirmed XIs and benches** ~1h before each kickoff, under the same match and player ids as UEFA Fantasy | public JSON |
| UCL | Understat (via `soccerdata`) | **recent form**: last-N domestic match logs (starts / minutes / goals / xG / xA) and season xG / xA / minutes, big-five leagues | scrape, best-effort |
| UCL | Sofascore (opt-in: `RECENT_FORM_SOURCE=sofascore\|both`) | last-N starts / minutes / goals / xG / rating across all competitions, season xG for every club | public JSON, TLS-impersonated; refuses this app since 2026-10 |
| UCL | Club-strength priors | attack / defence ratings → fixture difficulty, clean-sheet model | static table, self-tunes on results |
| **FPL Draft** | FPL / FPL-Draft API | prices, ownership, `chance_of_playing`, **editor news string** (aggregated presser notes), form, xG/xA, set-piece order, DefCon | public JSON |
| FPL | FPL official FDR + club-strength priors | position-aware fixture difficulty | public JSON + static table |
| **NFL** | ESPN Fantasy API | rosters, matchups, standings, **injury designations**, % started / rostered | cookie-auth JSON |
| NFL | FantasyPros | weekly + rest-of-season expert-consensus ranks | scrape (`var ecrData`) |
| NFL | ESPN public scoreboard | pro schedule, opponent, bye weeks | public JSON |
| NFL | Defensive-matchup table | pass- vs rush-defence strength → position matchup rating | static, self-tunes |
| **NBA** | ESPN Fantasy API (basketball) | league rules and scoring, rosters and daily lineup slots, matchups and live scores, standings, pickup limits | cookie-auth JSON (the NFL login works) |
| NBA | ESPN player pool (`kona_player_info`) | per-game averages in the league's scoring (ESPN projection, this season, last season, last 15 days), injury tags, % rostered and its trend | public JSON; league-scored when fetched in the league |
| NBA | ESPN pro schedule (`proTeamSchedules_wl`) | every NBA game by scoring period → games per matchup, light days, playoff-round games | public JSON |
| **ML (FPL)** | [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League) | seven seasons of per-fixture player history (training + backtest) | public CSV (code MIT, data © Premier League); downloaded at run time, never committed |

For **injury / team news**, the primary feed already carries an
official-club-derived signal: FPL's editor `news` field and UEFA's
`pStatus`/`qStatus` are updated from club statements and pressers. A dedicated
per-club scraper (below) would add lead time and detail.

---

## Roadmap — free, best-effort, one per row

Add a source by writing a module in `fantasy/leagues/ucl/sources/` that returns
`list[Signal]` keyed by our player id, then registering it in the relevant
`compose(...)` call. Nothing else changes; a source that fails returns `[]` and
the blend degrades gracefully.

### UCL / FPL (football)

| Source | Adds | Notes / risk |
|---|---|---|
| **Official club sites / X accounts** | confirmed XIs ~1h pre-KO, injury statements, "late fitness test" language | 20+ formats; start with the 6–8 clubs that matter for your leagues |
| Fantasy Football Scout — team news | predicted XIs, press-conference notes | full XIs are member-gated; the free team-news page is partial |
| FPLedits / FPL predicted lineups | expected XI + sub list + confidence | JS-rendered (Next.js) — needs a headless fetch or their internal API |
| Rotowire soccer lineups | predicted XI + confirmed flag | JS-rendered; per-match pages |
| ESPN soccer box scores (`site.api.espn.com`) | recent starts / minutes / goals outside the big five (Portugal, Netherlands, Turkey, Belgium …) | public JSON; names matched to UEFA's, no xG |
| Betting markets (anytime scorer / clean sheet / cards) | market-implied goal, assist, CS, card probabilities | free odds APIs need a key; scraping odds pages is brittle |
| PhysioRoom / Ben Dinnery injury table | return-date estimates for `stash & wait` | single page, fairly stable HTML |

### NBA

| Source | Adds | Notes / risk |
|---|---|---|
| **NBA official injury report** | game-day status (probable / questionable / out) an hour or so before tip | a PDF per day — parseable, but late |
| Projected minutes (Rotowire / FantasyLabs) | minutes when a starter sits — the biggest single-game swing | mostly paywalled |
| Vegas game totals / spreads | pace and blowout risk → per-game ceiling and floor | free-ish odds pages |
| Basketball-Reference game logs | per-game fantasy points for a real variance model | scrape, polite rate |

### NFL

| Source | Adds | Notes / risk |
|---|---|---|
| **Official team injury reports** (NFL.com / club sites) | Wed/Thu/Fri practice status, game-day actives | standard league format — most reliable of the set |
| Rotowire / RotoWorld player news | beat-writer snaps / target / touch trends | per-player news feed |
| FantasyPros start/sit + snap-count pages | expert start/sit %, snap share | same scrape pattern already used |
| Vegas team totals / spreads | game environment → boom/bust, garbage-time | free-ish odds pages |
| ESPN `kona_playercard` weekly | opponent-adjusted projection, matchup rank | already reachable via the ESPN client |
| Weather (kickoff conditions) | wind/precip → passing & kicking downgrades | free weather APIs, stadium lat/long table |

---

## Design rules

1. **Every source is optional.** A failed scrape logs and returns `[]`.
2. **Confidence, not just value.** A beat-writer tweet 30 min pre-KO outweighs a
   season minutes average — set `confidence` and, for news that goes stale,
   `half_life_h` on `compose`.
3. **Official club is always in the set** for injury / availability, and is
   given the highest confidence when present.
4. **Surface disagreement.** If `c.disagreement >= 0.33`, the UI should badge the
   player ("sources disagree — rotation risk"), not silently average it away.
