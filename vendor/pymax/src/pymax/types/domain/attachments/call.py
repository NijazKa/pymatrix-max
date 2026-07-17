from typing import Literal

from pydantic import Field

from pymax.types.domain.base import CamelModel

from .enums import AttachmentType


class CallAttachment(CamelModel):
    """Вложение звонка.

    :ivar type: Тип вложения.
    :vartype type: Literal[AttachmentType.CALL]
    :ivar duration: Длительность звонка.
    :vartype duration: int | None
    :ivar conversation_id: ID звонка или конференции.
    :vartype conversation_id: str | int | None
    :ivar contact_ids: ID участников звонка.
    :vartype contact_ids: list[int]
    """

    type: Literal[AttachmentType.CALL] = Field(alias="_type")
    duration: int | None = None
    conversation_id: str | int | None = None
    contact_ids: list[int] = Field(default_factory=list)
