from pymax.types.domain.base import CamelModel
from pymax.types.domain.presence import Presence


class PresenceEvent(CamelModel):
    """Событие изменения присутствия пользователя.

    :ivar presence: Новое состояние присутствия.
    :vartype presence: Presence
    :ivar user_id: ID пользователя.
    :vartype user_id: int
    """

    presence: Presence
    user_id: int
