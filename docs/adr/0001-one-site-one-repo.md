# 1. One site, one repository

**Status:** accepted · 2026-10

## Context

Three fantasy games (UCL Fantasy, FPL Draft, ESPN NFL) with different rules but
the same shape: pull data, project points, recommend moves. The question was
one site per game, or one for all.

## Decision

One site and one repository, with one folder per league inside a shared
backend (`backend/src/fantasy/leagues/{ucl,fpl,nfl}`) and frontend
(`frontend/src/features/{ucl,fpl,nfl}`).

## Consequences

* Shared pieces — auth, the home "command centre" that ranks alerts across
  leagues, settings, the optimizer and formation code, the UI kit, CI and the
  deploy — exist once.
* A league is still self-contained: its routes, views, schemas and pages live
  together, and each league's pages are a separate lazy-loaded chunk.
* One repo reads better as a portfolio piece than three thin ones, and the
  cross-league home page is only possible with one backend.
