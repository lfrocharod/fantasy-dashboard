"""The ASGI entrypoint Vercel loads (see vercel.json). The package is installed
from the src/ layout, so this file only re-exports the app."""

from fantasy.api.main import app

__all__ = ["app"]
