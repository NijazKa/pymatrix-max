from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .user import User


class BridgeSmsCodeProvider:
    """Провайдер SMS-кода для PyMax: вместо чтения из консоли ждёт ответ
    пользователя в его Matrix management-комнате."""

    def __init__(self, user: "User") -> None:
        self.user = user

    async def get_code(self, phone: str) -> str:
        return await self.user.wait_for_input(
            f"Max прислал SMS-код на {phone}. Введите его следующим сообщением:"
        )


class BridgePasswordProvider:
    """Провайдер пароля 2FA/мастер-пароля для PyMax: ждёт ответ пользователя
    в Matrix вместо getpass в консоли."""

    def __init__(self, user: "User") -> None:
        self.user = user

    async def get_password(self, hint: str | None = None) -> str:
        prompt = "Аккаунт Max требует пароль (мастер-пароль / 2FA)"
        if hint:
            prompt += f" — подсказка: {hint}"
        prompt += ". Введите пароль следующим сообщением:"
        return await self.user.wait_for_input(prompt)
