from pydantic import Field

from pymax.types.domain.base import CamelModel
from pymax.types.domain.message import ReactionCounter


class ReactionUpdateEvent(CamelModel):
    """Событие обновления реакций сообщения.

    MAX может присылать ``messageId`` как JSON-число или строку, а некоторые
    варианты уведомления не содержат counters/totalCount. Обработчик моста
    нормализует ID через ``str(...)`` и при необходимости запрашивает текущее
    состояние реакций отдельным точечным вызовом для конкретного сообщения.
    """

    message_id: int | str
    chat_id: int
    counters: list[ReactionCounter] = Field(default_factory=list)
    total_count: int = 0
