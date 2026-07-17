from typing import Any, Literal

from pydantic import Field

from pymax.types.domain.attachments import AttachmentType
from pymax.types.domain.base import CamelModel


class InlineKeyboardAttachment(CamelModel):
    """Вложение inline-клавиатуры.

    :ivar type: Тип вложения.
    :vartype type: Literal[AttachmentType.INLINE_KEYBOARD]
    :ivar keyboard: Данные inline-клавиатуры.
    :vartype keyboard: dict[str, Any]
    """

    type: Literal[AttachmentType.INLINE_KEYBOARD] = Field(alias="_type")
    keyboard: dict[str, Any]
