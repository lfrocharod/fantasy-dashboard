# fantasy (backend)

The Python half of the Fantasy Dashboard: the FastAPI app, the per-league data
pipelines and decision models, the learned FPL model, and the `fantasy` CLI
that ties them together. See the [top-level README](../README.md).

```bash
uv sync --extra jobs --extra ml          # everything (the API alone needs no extras)
uv run fantasy --help
TEST_DATABASE_URL=postgresql://… uv run pytest
```
