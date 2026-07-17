from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import PrivateAttr, model_validator

from pymax.logging import get_logger
from pymax.types.domain import Chat
from pymax.types.domain.base import CamelModel
from pymax.types.domain.message import Message

if TYPE_CHECKING:
    from pymax.api.messages import MessageService

logger = get_logger(__name__)


class MessageDeleteEvent(CamelModel):
    """Событие удаления сообщений.

    Handler ``on_message_delete`` получает этот объект, когда Max сообщает об
    удалении одного или нескольких сообщений в чате.

    :ivar message_ids: ID удаленных сообщений.
    :vartype message_ids: list[int]
    :ivar chat_id: ID чата.
    :vartype chat_id: int
    :ivar chat: Чат, если Max прислал полный объект.
    :vartype chat: Chat | None
    :ivar message: Удаленное сообщение для WebSocket-события.
    :vartype message: Message | None
    :ivar ttl: Признак удаления из-за TTL, если Max его прислал.
    :vartype ttl: bool
    """

    message_ids: list[int]
    chat_id: int
    chat: Chat | None = None
    message: Message | None = None
    ttl: bool = False

    _actions: MessageService | None = PrivateAttr(default=None)

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, data: Any) -> Any:
        # i really hate it cause of stupid web version thats send other type
        # of payload (128, expect 142)
        # TODO: impl it in the better way maybe

        if not isinstance(data, dict):
            return data

        if "chat" in data:  # case opcode == 142
            chat = data["chat"]
            chat_id = chat.get("id") if isinstance(chat, dict) else getattr(chat, "id", None)
            message_ids = data.get("messageIds", data.get("message_ids"))
            if chat_id is None or message_ids is None:
                return data

            return {
                "chat": chat,
                "ttl": data.get("ttl", False),
                "messageIds": message_ids,
                "chatId": chat_id,
            }
        if "message" in data:  # case opcode == 128
            message = data["message"]
            message_id = (
                message.get("id") if isinstance(message, dict) else getattr(message, "id", None)
            )
            chat_id = data.get("chatId", data.get("chat_id"))
            if chat_id is None or message_id is None:
                return data

            return {
                "chatId": chat_id,
                "message": message,
                "ttl": data.get("ttl", False),
                "messageIds": [message_id],
            }

        logger.warning("Illegal state during MessageDeleteEvent validation. Starting fallback")
        return data  # stupid fallback but who cares. Still better than KeyError

    def bind(self, actions: MessageService) -> MessageDeleteEvent:
        """Привязывает сервис сообщений к событию удаления."""
        self._actions = actions
        return self
