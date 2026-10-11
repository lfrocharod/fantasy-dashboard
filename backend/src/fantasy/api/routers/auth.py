"""Login / logout / session."""

from __future__ import annotations

import asyncio
import os
import time

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import Field

from fantasy.api.schemas.common import Ok, Schema
from fantasy.api.schemas.home import SessionInfo
from fantasy.api.security import (
    MAX_AGE_SECONDS,
    SESSION_COOKIE,
    LoginThrottle,
    create_session_token,
    demo_mode,
    password_ok,
    verify_session_token,
)

router = APIRouter(prefix="/api", tags=["auth"])
throttle = LoginThrottle()
MIN_LOGIN_SECONDS = 0.25  # timing doesn't reveal whether the hash check ran


class Login(Schema):
    password: str = Field(min_length=1, max_length=200)


@router.post("/auth", response_model=Ok)
async def login(body: Login, request: Request, response: Response) -> Ok:
    started = time.monotonic()
    client = request.client.host if request.client else "?"
    if throttle.blocked(client):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts — wait a few minutes")
    ok = await asyncio.to_thread(password_ok, body.password)
    wait = MIN_LOGIN_SECONDS - (time.monotonic() - started)
    if wait > 0:
        await asyncio.sleep(wait)
    if not ok:
        throttle.failed(client)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong password")
    throttle.reset(client)
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(),
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        secure=os.environ.get("COOKIE_SECURE", "1") != "0",
        samesite="lax",
        path="/",
    )
    return Ok()


@router.delete("/auth", response_model=Ok)
def logout(response: Response) -> Ok:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return Ok()


@router.get("/session", response_model=SessionInfo)
def session_info(request: Request) -> SessionInfo:
    demo = demo_mode()
    return SessionInfo(
        authenticated=demo or verify_session_token(request.cookies.get(SESSION_COOKIE)),
        demo=demo,
    )
