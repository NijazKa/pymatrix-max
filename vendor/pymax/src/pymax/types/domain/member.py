from .base import CamelModel
from .presence import Presence
from .user import User


class Member(CamelModel):
    """Пользователь из списка участников или заявок на вступление.

    :ivar contact: Данные пользователя.
    :vartype contact: User
    :ivar presence: Информация о присутствии пользователя.
    :vartype presence: Presence
    """

    contact: User
    presence: Presence
