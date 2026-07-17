from typing import Any, Literal

from pydantic import Field

from pymax.types.domain.base import CamelModel

from .enums import AttachmentType


class ShareAttachment(CamelModel):
    """Вложение предпросмотра ссылки.

    :ivar type: Тип вложения.
    :vartype type: Literal[AttachmentType.SHARE]
    :ivar url: URL ссылки.
    :vartype url: str | None
    :ivar title: Заголовок предпросмотра.
    :vartype title: str | None
    :ivar description: Описание предпросмотра.
    :vartype description: str | None
    :ivar image: Данные изображения предпросмотра.
    :vartype image: dict[str, Any] | None
    """

    type: Literal[AttachmentType.SHARE] = Field(alias="_type")
    url: str | None = None
    title: str | None = None
    description: str | None = None
    image: dict[str, Any] | None = None
