# Changelog

Notable changes, newest first. The app is versioned as a whole: a fix bumps the
patch, a feature the minor. Each version is a tag and a GitHub release.

## [Unreleased]

### Added
- A public, read-only [live demo](https://fantasy-dashboard-demo.vercel.app)
  of the anonymised dataset. It runs from its own database and database role.

## [2.1.3] — 2026-10-11

### Fixed
- **NBA:** the pickup limit is per matchup, scaled by the matchup's NBA game
  days when the league counts it per day — seven in an ordinary week, thirteen
  in the opening one, four around the All-Star break — instead of "one a day".
  The overview shows what's left; streams aren't suggested once it's used up.

## [2.1.2] — 2026-10-11

### Fixed
- **UCL:** the mini-league table and rival tracking work. Matchday points were
  read from field names UEFA doesn't send (every rival scored 0); the table is
  now requested the way UEFA's own site asks for it, paged, and re-resolved
  from the league code if the stored id is refused. The other half of the
  outage was a saved UEFA session that could read the squad but not leagues —
  a fresh login fixed it.
- **FPL:** the best XI can field two midfielders (5-2-3), as FPL Draft allows.

### Added
- A home-page alert when the UEFA login has expired.
- Conventions: commit subjects checked in CI, a pull-request template,
  [CONTRIBUTING.md](CONTRIBUTING.md), this changelog with tagged releases, and
  Dependabot for the pinned GitHub Actions.

## [2.1.1] — 2026-10-11

### Fixed
- **FPL:** the live gameweek panel fills again (the request ran on a closed
  HTTP client).

### Removed
- The Next.js app (`web/`), its drizzle migrations (`db/`) and the league
  state left in `settings` after its copy to real tables (migration 0004).

## [2.1.0] — 2026-10-11

### Added
- **NBA:** ESPN fantasy basketball (head-to-head points) — the best legal
  lineup for every day of the matchup, win probability, streaming add/drops
  that count only the games a pickup would start, games per matchup and light
  days, playoff odds, rival rosters and a trade lab.

## [2.0.0] — 2026-10-11

The rebuild: one repository, Python owns the numbers.

### Added
- A FastAPI backend serving every page, with SQLAlchemy models and Alembic
  migrations (the original schema stamped as the baseline).
- A React + TypeScript + Vite single-page app on a client generated from the
  API's OpenAPI schema.
- A learned FPL points model (gradient-boosted trees), walk-forward
  backtested over four seasons and graded live every gameweek.
- A deterministic demo dataset, Docker images, CI on every push and a home
  runner on systemd timers.

### Changed
- The decision logic moved from the browser to Python, checked against the
  original TypeScript with parity goldens.
- Hosting moved to Vercel's free tier (an earlier Cloud Run setup needed a
  billing account).

## [1.0.0] — 2026-10-10

The original Next.js app over Postgres, fed by a Python ingest job.

### Added
- **UCL Fantasy:** projections from minutes, team strength and form, an
  integer-programming optimizer, chips and captaincy, the mini-league, live
  matchdays and model calibration.
- **FPL Draft:** player board, rotation planner, waivers, trade lab, rival
  rosters and simulated standings.
- **NFL (ESPN):** a draft-night board, then the in-season league — lineups,
  streaming, trades and playoff odds.
- A cross-league home page with deadline checklists and alerts.

[Unreleased]: https://github.com/lfrocharod/fantasy-dashboard/compare/v2.1.3...HEAD
[2.1.3]: https://github.com/lfrocharod/fantasy-dashboard/compare/v2.1.2...v2.1.3
[2.1.2]: https://github.com/lfrocharod/fantasy-dashboard/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/lfrocharod/fantasy-dashboard/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/lfrocharod/fantasy-dashboard/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/lfrocharod/fantasy-dashboard/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/lfrocharod/fantasy-dashboard/releases/tag/v1.0.0
