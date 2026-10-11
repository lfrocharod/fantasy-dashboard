# 3. Python owns the numbers; the browser only renders

**Status:** accepted · 2026-10

## Context

The first version computed a lot inside React pages — FPL trade evaluation,
NFL playoff simulations, lineup optimisation — in TypeScript, next to a Python
pipeline that computed the rest. Logic was split across two languages and
untestable where it mattered.

## Decision

* Every number, verdict and checklist is computed in Python and exposed by
  FastAPI with Pydantic response models; the SPA formats, sorts and filters.
* The TypeScript client types are **generated** from the OpenAPI schema; CI
  fails if they drift, so a backend change that breaks a page fails `tsc`.
* The TypeScript logic was ported with **parity goldens**: outputs recorded
  from the original code on fixed inputs, asserted against the Python port
  (including JavaScript's rounding semantics) before the old code was removed.
* Schema changes go through Alembic, expand/contract: the old app kept working
  on the same database until cutover.

## Consequences

* The decision logic is unit-tested in one place (pytest), and the API is
  usable without the UI.
* A little more API surface; each page is one typed request.
