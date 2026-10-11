# 2. Collect at home, serve from the cloud

**Status:** accepted · 2026-10

## Context

UEFA's and ESPN's edges block datacenter IP ranges, so a cloud scheduler can't
fetch the UCL or NFL data. The app itself should be always available and cost
nothing when idle.

## Decision

Split by direction: **reads** are served by Cloud Run (scales to zero), and
**writes** come from systemd timers on a home machine that run the same
`fantasy` CLI the containers use. The runner is a clean clone of `main` that
fast-forwards before each run, so there is one deploy path — merge to `main`.

## Consequences

* Data freshness depends on the home machine being awake. Missed runs catch up
  on wake; the home page flags stale leagues; failures push to a phone.
* The jobs image still exists (migrations, and any source that turns out to be
  reachable from the cloud can move to a Cloud Run job without code changes).
* Secrets for the syncs live only on that machine (mode 600), not in CI.
