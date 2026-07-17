from .base import CamelModel


class Presence(CamelModel):
    """Состояние присутствия пользователя.

    :ivar seen: Время последней активности в формате Unix time, если оно
        передано сервером.
    :vartype seen: int | None
    :ivar status: Код статуса присутствия Max, если он передан сервером.
    :vartype status: int | None
    """

    seen: int | None = None
    status: int | None = None
