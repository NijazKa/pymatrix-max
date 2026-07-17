from typing import Literal

from pydantic import Field

from pymax.types.domain.base import CamelModel

from .enums import AttachmentType


class PhotoAttachment(CamelModel):
    """Фото-вложение сообщения.

    Используйте этот тип для входящих фото в ``Message.attaches``. Для отправки
    нового фото используйте ``pymax.Photo`` из ``pymax.files``.

    Example:
        .. code-block:: python

           for attach in message.attaches:
               if isinstance(attach, PhotoAttachment):
                   print(attach.photo_id, attach.base_url)

    :ivar base_url: URL фотографии.
    :vartype base_url: str
    :ivar height: Высота изображения.
    :vartype height: int
    :ivar width: Ширина изображения.
    :vartype width: int
    :ivar photo_id: ID фотографии.
    :vartype photo_id: int
    :ivar photo_token: Токен фотографии.
    :vartype photo_token: str
    :ivar preview_data: Данные превью.
    :vartype preview_data: bytes | None
    :ivar type: Тип вложения.
    :vartype type: Literal[AttachmentType.PHOTO]
    """

    base_url: str
    height: int
    width: int
    photo_id: int
    photo_token: str
    preview_data: bytes | None = None
    type: Literal[AttachmentType.PHOTO] = Field(alias="_type")
