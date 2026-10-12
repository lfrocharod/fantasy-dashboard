# Working on fantasy-dashboard

One person's project, run like a team's: every change goes through a pull
request, CI and a preview deploy before it reaches `main`, which deploys.

## The loop

1. **Branch** from `main`: `feat/…`, `fix/…`, `docs/…`, `ci/…`.
2. **Commit** with [Conventional Commits](https://www.conventionalcommits.org/)
   subjects: `type(scope): summary`, lower case, no trailing full stop, at
   most 72 characters. The body says what changed and why, wrapped at 72
   columns. Sign commits (`git config commit.gpgsign true`).
3. **Open a pull request.** CI lints, type-checks and tests both halves, checks
   the generated API client and the commit subjects, and builds the images;
   Vercel deploys a preview of the branch.
4. **Squash-merge** once the checks pass. The pull request title, followed by
   its number, becomes the commit subject on `main`, so it follows the same
   convention. One commit per change.
5. **Release.** Each version is a signed tag and a GitHub release, recorded in
   [CHANGELOG.md](CHANGELOG.md): a fix bumps the patch, a feature the minor.

`main` is protected. Changes arrive only as pull requests whose checks are
green, merged by squash, so the history stays linear. Commits must be signed.
Force pushes and deletion are blocked.

## Types and scopes

| Type | For |
|---|---|
| `feat` | something a user can do or see that they couldn't before |
| `fix` | wrong behaviour made right |
| `perf`, `refactor` | faster, or restructured with no change in behaviour |
| `docs`, `test` | documentation, tests only |
| `build`, `ci` | the image, dependencies, deployment / the workflows |
| `chore` | everything else (removals, housekeeping) |

Scopes name the part of the app: `ucl`, `fpl`, `nfl`, `nba`, `home`, `api`,
`frontend`, `backend`, `ml`, `deploy`. Leave the scope out for a change that
spans leagues.

## Checks to run locally

```bash
cd backend && uv run ruff check src tests && uv run mypy src \
  && TEST_DATABASE_URL=postgresql://… uv run pytest
cd frontend && npm run typecheck && npm run lint && npm test
# after an API change: regenerate the client and commit both files
uv run --project ../backend fantasy openapi > openapi.json && npm run api
```
