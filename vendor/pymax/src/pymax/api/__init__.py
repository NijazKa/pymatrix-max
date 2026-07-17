from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .facade import ApiFacade

__all__ = ("ApiFacade",)


def __getattr__(name: str) -> object:
    if name == "ApiFacade":
        from .facade import ApiFacade

        return ApiFacade

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
