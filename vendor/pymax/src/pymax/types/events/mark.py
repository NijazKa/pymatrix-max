from pymax.types.domain.base import CamelModel


class MessageReadEvent(CamelModel):
    """Событие изменения отметки прочтения чата.

    Handler ``on_message_read`` получает объект, когда пользователь отмечает
    сообщения прочитанными или возвращает чат в непрочитанное состояние.

    :ivar set_as_unread: Чат был явно отмечен непрочитанным.
    :vartype set_as_unread: bool
    :ivar chat_id: ID чата.
    :vartype chat_id: int
    :ivar user_id: ID пользователя, изменившего отметку.
    :vartype user_id: int
    :ivar mark: Временная отметка прочтения Max.
    :vartype mark: int
    """

    set_as_unread: bool
    chat_id: int
    user_id: int
    mark: int
