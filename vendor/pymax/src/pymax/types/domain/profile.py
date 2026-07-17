from .base import CamelModel
from .user import User


class Profile(CamelModel):
    """Профиль текущего аккаунта.

    :ivar contact: Контакт текущего аккаунта.
    :vartype contact: User
    :ivar profile_options: Дополнительные флаги профиля текущего аккаунта.
    :vartype profile_options: list[int] | None
    """

    contact: User
    profile_options: list[int] | None = None
