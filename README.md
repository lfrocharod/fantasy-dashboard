# Fantasy Dashboard

A private web app to help win my fantasy leagues. **v1 covers the UEFA Champions
League Fantasy game** (classic scoring, mini-league against friends): unified
dashboard, projected points (xPts) for start/sit, a free-agent / transfer finder,
a formation-constrained lineup + captain optimizer, and mini-league analytics.
Built so ESPN NFL/NBA and FPL Draft can be added later as extra modules.

- **Web + DB are free & hosted**: Vercel Hobby + Neon Postgres.
- **Ingestion runs from your own machine.** UEFA's edge (Akamai) blocks
  datacenter IPs, so GitHub Actions / Vercel cannot fetch the Fantasy feeds —
  only a residential connection can. One command (`ingest/run.sh`), on demand or
  from a `cron` entry.

```
web/     Next.js app (dashboard + API) — deploys to Vercel, root dir "web"
ingest/  Python job: UEFA feeds + FBref/Understat xG -> projections + optimizer,
         written to Postgres. Run locally via ingest/run.sh.
db/      Generated SQL migration (drizzle-kit)
```

## How it fits together

```
your laptop                          Vercel (Next.js)              you
  ingest/run.sh  ──writes──▶   Neon Postgres  ◀──reads──   dashboard / pages
       │                              ▲
       ├─ gaming.uefa.com feeds       │  league code · GUID · session cookie
       └─ FBref + Understat (xG/xA) ──┘     (entered in the app's Settings)
```

The web app only reads Postgres. `ingest/run.sh` is the only thing that talks to
UEFA, and it must run from a home connection.

### What needs auth

| Data | Source | Auth |
|---|---|---|
| Players, prices, ownership, fixtures, deadlines | `services/feeds/*_90_*.json` | none |
| Your squad, mini-league standings | `services/api/...` | `entity` header (baked in) **+ your browser session cookie** |

So projections, the players table and the free-agent finder work with no login;
only your squad and the league table need the cookie.

---

## Deploy (one-time)

### 1. Neon
Create a free project → copy the **pooled** connection string
(`...-pooler.<region>.neon.tech`).

### 2. Vercel
Import the repo, **Root Directory = `web`**, add env vars:

| Name | Value |
|------|-------|
| `DATABASE_URL` | Neon pooled string |
| `APP_PASSWORD_HASH` | `cd web && npm i && npm run hash-password 'your password'` |
| `SESSION_SECRET` | `node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"` |
| `WEB_CRYPTO_KEY` | `node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"` |

### 3. Create the tables
```bash
cd web && npm install
# put DATABASE_URL (+ the 3 secrets) in web/.env.local
npm run db:push
```

### 4. First ingestion (from your laptop)
```bash
cd ingest
./run.sh --skip-sources         # fast: players, fixtures, projections
./run.sh                        # full: also scrapes FBref/Understat xG (~3-5 min)
```
`run.sh` reads `DATABASE_URL` + `WEB_CRYPTO_KEY` from `../web/.env.local`, creates
its venv on first run, and writes to Neon. The hosted app updates immediately.

### 5. Connect your UEFA account (for squad + mini-league)
In the app → **Settings**:

- **Mini-league code** — e.g. `DEMO42` (the invite code). Auto-filled from
  UEFA's config on the first run; set it if it isn't.
- **Your UEFA GUID** — sign in at gaming.uefa.com, DevTools → Network, open any
  `services/api/Gameplay/user/<GUID>/…` request; the `<GUID>` in the path.
- **UEFA session cookie** — same DevTools view, that request's **Request
  Headers → `Cookie:`** value. Paste the whole string. Stored AES-GCM encrypted.

Then run `./run.sh` again — it resolves the league id from the code, pulls your
squad and the standings, and the optimizer starts producing transfer advice.
The cookie expires after a while; when Settings shows `public_only`, re-paste it.

### Keeping it fresh
Add a cron entry on your machine (runs when the laptop is on):
```cron
*/30 8-23 * * *  cd ~/fantasy-dashboard/ingest && ./run.sh --skip-sources >> /tmp/ingest.log 2>&1
7 6 * * *        cd ~/fantasy-dashboard/ingest && ./run.sh >> /tmp/ingest.log 2>&1
```

## The projection model

`ingest/fantasy_ingest/model/projections.py`, per player per matchday:

- **Minutes** from availability + season minutes share.
- **Team match xG / xGA** from multiplicative attack/defence ratings
  (`team_strength.py`) × home advantage; Poisson for clean-sheet probability.
- **Attacking pts** from `npxG/90` + `xAG/90` (FBref + Understat), scaled by
  opponent leakiness, into UEFA's per-position scoring.
- **Defensive pts** — clean sheet, expected goals-conceded drag, GK saves.
- **Recoveries, appearance, discipline, MOTM** contributions.
- Blended with UEFA's season points-per-game (30% by default; tune in Settings →
  model parameters, e.g. `{"form_weight":0.25,"horizon":3}`).
- Output: `xpts`, `xpts_captain`, `value` (xpts/€), simulated floor/ceiling.

The **optimizer** (`model/optimizer.py`, CBC ILP) picks the best legal XI +
captain and runs a greedy transfer planner over a matchday horizon, subtracting
the −4 hit for the second+ transfer.

## Local development

```bash
cd web && npm install && npm run dev          # needs web/.env.local

cd ingest
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m fantasy_ingest.run --samples ./samples --dry-run  # offline
.venv/bin/pytest -q
```

`ingest/samples/` holds trimmed real feeds; `--dry-run` writes nothing.

## Endpoint overrides

All UEFA URLs live in `ingest/fantasy_ingest/ucl/client.py`. If UEFA bumps the
competition id from `90` next season, set `UEFA_COMP_ID` in `ingest/.env`. Other
overrides: `UEFA_FEEDS_BASE`, `UEFA_API_BASE`, `UEFA_ENTITY`.

## Status / limitations

- **Ingestion is laptop-only** (UEFA blocks datacenter IPs). The
  `.github/workflows/ingest.yml` is kept only for a future self-hosted runner.
- No live in-match scoring — refresh before the deadline.
- One user, one password.
