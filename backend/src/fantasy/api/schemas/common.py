"""Base model + small shapes shared across leagues."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Schema(BaseModel):
    """snake_case in Python, camelCase on the wire."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        serialize_by_alias=True,
        # a response always carries its defaulted fields — say so in the
        # OpenAPI schema, so the generated client types them as present
        json_schema_serialization_defaults_required=True,
    )


Tone = Literal["good", "warn", "bad", "accent", "muted"]


class CheckItem(Schema):
    """One line of an OK / DO checklist."""

    ok: bool
    text: str
    href: str | None = None
    link_text: str | None = None


class Ok(Schema):
    ok: bool = True


class Range(Schema):
    lo: float
    hi: float
