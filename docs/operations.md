# Operations

Where everything runs, how data stays fresh with nobody touching it, and the
few things that do need a human.

## Moving parts

| Piece | Runs on | What it does |
|---|---|---|
| **App** — the React SPA + the FastAPI API | Vercel (Hobby plan), one project with two services | The SPA is static files on Vercel's CDN; `/api/*` runs FastAPI as a Python function in `cle1` (Cleveland), next to the database. Reads the database; the only writes are your settings and the draft board. |
| **Database** | Neon Postgres (AWS us-east-2) | Everything. Schema owned by Alembic (`backend/src/fantasy/migrations`). |
| **Syncs** | systemd user timers on a home machine | Pull every league's data, rebuild projections, write the database. Home on purpose: UEFA's and ESPN's edges block datacenter IPs. |
| **CI** | GitHub Actions, every push | Lint, types, tests (Postgres 18), the generated API client check, both Docker images and an API smoke test. |
| **Deploys** | Vercel's Git integration | Every push builds a preview; `main` builds production, which runs `fantasy db upgrade` before the new version takes traffic. |

## The schedule (nothing to run by hand)

| Timer | When (local) | Runs |
|---|---|---|
| `fantasy-sync-fast` | every 30 min, 06:00–23:30 | `fantasy sync all --mode fast` — feeds, prices, lineups, projections, the optimizer; FPL live gameweek and ESPN scores |
| `fantasy-sync-full` | daily 05:40 | `fantasy sync all --mode full` — the same plus the recent-form / xG scrape and model calibration |
| `fantasy-sync-live` | every 5 min, 09:00–18:55 | `fantasy sync ucl --mode live --if-live` — live matchday refresh; exits at once unless a Champions League match is in play |
| `fantasy-ml-train` | Mondays 04:30 | `fantasy ml train` — refits the learned FPL model |

The runner works from its own clone (`~/.local/share/fantasy-dashboard/runner`)
and resets it to `main` before every fast/full run — merging to `main` ships
both the app (via Vercel) and the pipelines (via the runner). A `flock`
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
  `SWID` cookies (NFL → Draft board → Setup; basketball uses the same ones
  unless it has its own) and the optional FPL Draft token expire every few
  weeks. Settings shows the UEFA state; the home page flags a
  league that stops updating. Re-paste in the app — the next sync uses it.
* **Draft night.** `fantasy draft-board --sport nfl --sync --loop 15` follows
  live ESPN picks every 15 seconds for the evening.
* **A new season for the ML model.** Add the finished season to
  `SEASONS` in `backend/src/fantasy/ml/history.py`, re-run the backtest
  (`fantasy ml backtest`) and commit the updated report.

## How a deploy works

`vercel.json` declares two services in one Vercel project:

* **web** — `frontend/`, built by Vite, served from the CDN. Unknown paths fall
  back to `index.html` so client-side routes load; hashed assets are cached for
  a year.
* **api** — `backend/`, FastAPI as one Python function (`backend/asgi.py`).
  Vercel installs the base dependencies from `uv.lock` (no extras, no dev
  tools: ~155 MB of a 500 MB limit). Its build step runs
  `fantasy db upgrade` on production builds only — previews never migrate the
  shared database. The existing database is recognised and stamped on the
  first run, then upgraded.

`/api/*` goes to the API, everything else to the SPA, on one origin (no CORS;
the session cookie just works). Migrations must stay backward compatible with
the version still serving while a build runs (add, backfill, and only drop in a
later release).

## Setting it up from scratch

1. **Database.** A Neon Postgres database (the free plan is plenty). Note its
   connection string.
2. **App.** Import the repository into Vercel. Settings → Build and
   Deployment: *Framework Preset* → **Services**, *Root Directory* → empty.
   Environment variables: `DATABASE_URL`, `SESSION_SECRET` (any long random
   string), `APP_PASSWORD_HASH` (a bcrypt hash of your password) and
   `WEB_CRYPTO_KEY` (32 random bytes, base64). Deploy: the build creates the
   schema.
3. **Syncs.** Put `DATABASE_URL` and `WEB_CRYPTO_KEY` in a file and run
   ```bash
   infra/home/install.sh --from-env that-file
   ```
   It clones the runner, writes `~/.config/fantasy-dashboard/env` (mode 600),
   migrates, installs and starts the timers, and trains the FPL model once.
   Add `NTFY_TOPIC=…` to that env file for phone alerts.
4. **Leagues.** Sign in and connect each one: the UEFA login in Settings, the
   FPL Draft league and entry on the FPL overview, the ESPN league and cookies
   in NFL → Draft board → Setup, and basketball in NBA → Setup (paste your
   ESPN team page URL; it reuses the NFL cookies). The next sync pulls them.

## Public demo

<https://fantasy-dashboard-demo.vercel.app> is a second Vercel project built
from the same repository and commits. It serves the anonymised demo dataset
with `DEMO_MODE=1`: no sign-in, and every endpoint that writes answers 403.

* **Database.** The demo has its own database, `fantasy_demo`, on the same Neon
  server. It belongs to its own login role, so the public deployment holds no
  credential that can reach production:
  ```sql
  create role fantasy_demo login password '…';
  grant fantasy_demo to current_user;  -- needed to create a database it owns
  create database fantasy_demo owner fantasy_demo;
  ```
  With that role's connection string, migrate it and load the dataset:
  `uv run fantasy db upgrade && uv run fantasy demo seed`. The seed wipes
  league data first, and the role keeps it away from the real database.
* **Vercel.** Import the repository a second time: *Framework Preset* →
  **Services**, *Root Directory* → empty. Set two variables, `DATABASE_URL`
  (the demo role's) and `DEMO_MODE=1`. Then set Settings → Git → *Ignored Build
  Step* → **Only build production**, so a pull request gets one preview, not
  two.
* **Upkeep.** Production builds of the demo migrate its database, as they do
  the real one. Re-run `fantasy demo seed` when what the demo shows changes.
  `fantasy demo record` refreshes the recorded public data first.

## Secrets

| Secret | Lives in | Rotate |
|---|---|---|
| `DATABASE_URL`, `SESSION_SECRET`, `APP_PASSWORD_HASH`, `WEB_CRYPTO_KEY` | Vercel environment variables (app) and `~/.config/fantasy-dashboard/env` (runner: the first and last) | change them in Vercel → Settings → Environment Variables and redeploy; edit the runner's file |
| League cookies / tokens | the database, AES-GCM encrypted with `WEB_CRYPTO_KEY` | re-paste in the app |
| The demo's `DATABASE_URL` (role `fantasy_demo`) | the demo project's Vercel variables and `~/.config/fantasy-dashboard/demo.env` | `alter role fantasy_demo password '…'`, then update both |

Nothing secret lives in GitHub — CI needs none, and Vercel deploys through its
own GitHub app.

## Cost

Nothing, and no card on file anywhere: Vercel's Hobby plan (free, for
non-commercial use) serves the app and the demo, Neon's free plan holds both
databases, GitHub Actions is free for a public repository, and the syncs run
at home. A personal dashboard stays far inside every free allowance.
