from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel

from pymax.types.domain import Chat, Message, User
from pymax.types.events import MessageDeleteEvent

if TYPE_CHECKING:
    from pymax.app import App


T = TypeVar("T")


def bind_api_model(app: App, value: T) -> T:
    _bind_api_value(app, value, set())
    return value


def bind_api_models(app: App, values: Iterable[T]) -> list[T]:
    return [bind_api_model(app, value) for value in values]


def _bind_api_value(app: App, value: Any, seen: set[int]) -> None:
    if value is None or isinstance(value, (str, bytes)):
        return

    value_id = id(value)
    if value_id in seen:
        return

    seen.add(value_id)

    if isinstance(value, Message):
        value.bind(app.api.messages)
    elif isinstance(value, Chat):
        value.bind(app.api.messages, app.api.chats)
    elif isinstance(value, User):
        value.bind(app.api.users)
    elif isinstance(value, MessageDeleteEvent):
        value.bind(app.api.messages)

    if isinstance(value, BaseModel):
        for field_name in value.__class__.model_fields:
            _bind_api_value(app, getattr(value, field_name, None), seen)

        for extra_value in (value.model_extra or {}).values():
            _bind_api_value(app, extra_value, seen)
    elif isinstance(value, Mapping):
        for item in value.values():
            _bind_api_value(app, item, seen)
    elif isinstance(value, Iterable):
        for item in value:
            _bind_api_value(app, item, seen)
