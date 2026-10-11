"""The FastAPI application: the JSON API under /api, and the built React app
for every other path (one origin — no CORS, cookie auth just works).

    fantasy serve --reload         # dev (the Vite dev server proxies /api here)
    uvicorn fantasy.api.main:app   # what the container runs
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

from fantasy import __version__
from fantasy.api.routers import auth, draft, fpl, health, home, nfl, settings, ucl

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}


def _operation_id(route: APIRoute) -> str:
    # "ucl_overview" rather than "overview_api_ucl_overview_get" in the client
    tag = route.tags[0] if route.tags else "api"
    return f"{tag}_{route.name}"


def _frontend_dir() -> Path | None:
    configured = os.environ.get("FRONTEND_DIST")
    candidates = [Path(configured)] if configured else []
    candidates.append(Path(__file__).resolve().parents[4] / "frontend" / "dist")
    return next((c for c in candidates if (c / "index.html").is_file()), None)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Fantasy Dashboard API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        generate_unique_id_function=_operation_id,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response: Response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    for r in (health, auth, home, settings, ucl, fpl, nfl, draft):
        app.include_router(r.router)

    dist = _frontend_dir()
    if dist is not None:
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        index = dist / "index.html"

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> Response:
            if path.startswith("api/"):
                return JSONResponse({"detail": "not found"}, status_code=404)
            static = (dist / path).resolve()
            if path and static.is_file() and dist.resolve() in static.parents:
                return FileResponse(static)
            # client-side routes all get the app shell
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
