from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .models import AuthResult

if TYPE_CHECKING:
    from pymax.app import App


class AuthFlow(Protocol):
    """Протокол полного пользовательского сценария авторизации.

    Используйте полный ``AuthFlow`` только для нестандартной авторизации. Для
    обычных случаев проще заменить ``SmsCodeProvider``, ``PasswordProvider`` или
    ``QrHandler``.

    Example:
        .. code-block:: python

           from pymax import Client
           from pymax.app import App
           from pymax.auth.models import AuthResult

           class StaticTokenFlow:
               async def authenticate(self, app: App) -> AuthResult:
                   return AuthResult(token="TOKEN")

           client = Client(
               phone="+79990000000",
               auth_flow=StaticTokenFlow(),
           )
    """

    async def authenticate(self, app: App) -> AuthResult:
        """Возвращает результат авторизации для новой локальной сессии."""
        ...
