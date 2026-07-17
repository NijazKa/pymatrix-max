from pymax.types.domain.base import CamelModel


class TypingEvent(CamelModel):
    """Событие набора текста пользователем.

    :ivar chat_id: ID чата.
    :vartype chat_id: int
    :ivar user_id: ID пользователя, который набирает текст.
    :vartype user_id: int
    """

    chat_id: int
    user_id: int
