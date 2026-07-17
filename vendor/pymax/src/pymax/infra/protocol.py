from typing import Protocol

from pymax.app import App


class IClientProtocol(Protocol):
    """Описывает минимальный клиент, нужный infra-миксинам."""

    _app: App
