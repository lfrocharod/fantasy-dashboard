# 2. Collect at home, serve from the cloud

**Status:** accepted · 2026-10

## Context

UEFA's and ESPN's edges block datacenter IP ranges, so a cloud scheduler can't
fetch the UCL or NFL data. The app itself should always be up, and the whole
thing is a personal project: it should cost nothing, with no card on file
anywhere.

## Decision

Split by direction. **Writes** come from systemd timers on a home machine that
run the `fantasy` CLI from a clean clone of `main`, reset before each run.
**Reads** are served by Vercel on the free Hobby plan, as one project with two
services: the Vite build on the CDN and FastAPI as a Python function in the
region next to the Neon database. A production build migrates the database
before the new version takes traffic, so there is one deploy path: merge to
`main`.

## Alternatives considered

* **Google Cloud Run** for the API. It scales to zero and runs the same
  container image, but it needs a billing account (a card) even inside the
  free tier.
* **A free container host** (Render, Koyeb and the like). Their free tiers
  sleep the container after a few idle minutes and take tens of seconds to wake,
  which is the wrong trade for a dashboard you open for one quick look.
* **Serving from the home machine through a tunnel.** It needs no cloud at
  all, but the site would be down whenever the laptop sleeps.

## Consequences

* Data freshness depends on the home machine being awake. Missed runs catch up
  on wake; the home page flags stale leagues; failures push to a phone.
* The API must fit a serverless function: no background threads, no local
  disk state, slim dependencies (the optimizer, scrapers and ML stack are
  extras the function never installs; their results reach it through the
  database). A cold start costs about a second and a half.
* The Docker image remains the self-contained way to run everything (the local
  stack and CI's smoke test), so moving to a container host later is a config
  change, not a rewrite.
* Secrets for the syncs live only on that machine (mode 600); the app's live in
  Vercel's environment variables; CI needs none.

## Update — 2026-10-15

A probe from a GitHub-hosted runner found ESPN's fantasy API, FPL, FantasyPros,
Understat and UEFA's match centre all reachable; only UEFA's fantasy API
(`gaming.uefa.com`) still refuses cloud IPs (it times out). FPL, NFL and NBA can
therefore also sync from GitHub Actions (`cloud-sync.yml`, opt-in), which
leaves only the Champions League dependent on the home machine.
