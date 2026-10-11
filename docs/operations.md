# Operations

Where everything runs, how data stays fresh with nobody touching it, and the
few things that do need a human.

## Moving parts

| Piece | Runs on | What it does |
|---|---|---|
| **App** — FastAPI + the built React SPA | Google Cloud Run (`fantasy`, us-east5) | Serves the site and the JSON API. Reads the database; the only writes are your settings and the draft board. Scales to zero. |
| **Database** | Neon Postgres (AWS us-east-2) | Everything. Schema owned by Alembic (`backend/src/fantasy/migrations`). |
| **Syncs** | systemd user timers on a home machine | Pull every league's data, rebuild projections, write the database. Home on purpose: UEFA's and ESPN's edges block datacenter IPs. |
| **CI** | GitHub Actions, every push | Lint, types, tests (Postgres 18), the generated API client check, both images. |
| **Deploys** | GitHub Actions, CI green on `main` | Images → Artifact Registry → `fantasy db upgrade` as a Cloud Run job → the service. Keyless (Workload Identity Federation). |

## The schedule (nothing to run by hand)

| Timer | When (local) | Runs |
|---|---|---|
| `fantasy-sync-fast` | every 30 min, 06:00–23:30 | `fantasy sync all --mode fast` — feeds, prices, lineups, projections, the optimizer; FPL live gameweek and ESPN scores |
| `fantasy-sync-full` | daily 05:40 | `fantasy sync all --mode full` — the same plus the recent-form / xG scrape and model calibration |
| `fantasy-sync-live` | every 5 min, 09:00–18:55 | `fantasy sync ucl --mode live --if-live` — live matchday refresh; exits at once unless a Champions League match is in play |
| `fantasy-ml-train` | Mondays 04:30 | `fantasy ml train` — refits the learned FPL model |

The runner works from its own clone (`~/.local/share/fantasy-dashboard/runner`)
and fast-forwards it to `main` before every fast/full run — merging to `main`
ships both the app (via Deploy) and the pipelines (via the runner). A `flock`
keeps runs from overlapping; a live tick that finds a long run going just skips.

```bash
systemctl --user list-timers 'fantasy-*'          # what runs next
journalctl --user -u 'fantasy-sync@*' -f          # follow the logs
systemctl --user start fantasy-sync@fast          # run one now
```

**Failures** push a phone notification when `NTFY_TOPIC` is set in
`~/.config/fantasy-dashboard/env` (subscribe to the topic in the ntfy app). The
home page also flags any league whose data is going stale.

**Asleep or offline?** Missed fast/full runs catch up as soon as the machine
wakes (`Persistent=true`); live ticks during the outage are simply lost. For
match nights, keep the machine awake — or install the runner on anything
always-on (a Raspberry Pi works: `infra/home/install.sh` is all it needs).

## What does need a human

* **Expired logins.** The UEFA session cookie (Settings), the ESPN `espn_s2` /
  `SWID` cookies (NFL → Draft board → Setup) and the optional FPL Draft token
  expire every few weeks. Settings shows the UEFA state; the home page flags a
  league that stops updating. Re-paste in the app — the next sync uses it.
* **Draft night.** `fantasy draft-board --sport nfl --sync --loop 15` follows
  live ESPN picks every 15 seconds for the evening.
* **A new season for the ML model.** Add the finished season to
  `SEASONS` in `backend/src/fantasy/ml/history.py`, re-run the backtest
  (`fantasy ml backtest`) and commit the updated report.

## One-time setup / cutover

1. **Google Cloud** — a project with billing, then
   ```bash
   gcloud auth login
   infra/gcp/bootstrap.sh --project MY_PROJECT --secrets-from ~/fantasy-dashboard/web/.env.local
   ```
   Idempotent: registry, service accounts, Workload Identity Federation, the
   four secrets, and the GitHub variables the Deploy workflow reads. Add
   `--demo-database-url URL` (a separate, empty Neon database) to also deploy
   the public read-only demo.
2. **Merge to `main`.** CI runs; Deploy builds, migrates Neon (the existing
   database is recognised and stamped, then upgraded) and deploys. Sign in at
   the Cloud Run URL with the same password — sessions carry over.
3. **Switch the syncs** to the new pipeline:
   ```bash
   infra/home/install.sh --from-env ~/fantasy-dashboard/web/.env.local
   ```
   Clones the runner, writes `~/.config/fantasy-dashboard/env` (mode 600),
   installs and starts the timers, trains the FPL model once, and retires the
   old `ingest/` timers and cron lines.
4. **Retire the old site** — remove the Vercel project, delete `web/` and
   `ingest/`, and ship the migration that drops the legacy `settings` keys
   (they're kept until now so the old site keeps working mid-cutover).

## Secrets

| Secret | Lives in | Rotate |
|---|---|---|
| `DATABASE_URL`, `SESSION_SECRET`, `APP_PASSWORD_HASH`, `WEB_CRYPTO_KEY` | Secret Manager (app) and `~/.config/fantasy-dashboard/env` (runner: the first and last) | change the file, re-run `bootstrap.sh --secrets-from …`, then run the Deploy workflow |
| League cookies / tokens | the database, AES-GCM encrypted with `WEB_CRYPTO_KEY` | re-paste in the app |

Nothing secret lives in GitHub: Deploy authenticates through Workload Identity
Federation, scoped to this repository's `main` branch.

## Cost

Built to sit inside free tiers: Cloud Run scales to zero (a personal app stays
far below the monthly free requests / CPU), Artifact Registry keeps the 5 most
recent images, Neon's free plan holds the database, and the syncs run at home.
