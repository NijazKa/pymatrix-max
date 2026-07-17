from typing import Literal

from pydantic import Field

from pymax.types.domain.base import CamelModel

from .enums import AttachmentType


class ControlAttachment(CamelModel):
    """Служебное вложение управления.

    :ivar type: Тип вложения.
    :vartype type: Literal[AttachmentType.CONTROL]
    :ivar event: Событие управления.
    :vartype event: str
    """

    type: Literal[AttachmentType.CONTROL] = Field(alias="_type")
    event: str
