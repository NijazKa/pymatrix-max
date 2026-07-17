from typing import Literal

from pydantic import Field

from pymax.types.domain.base import CamelModel

from .enums import AttachmentType


class FileAttachment(CamelModel):
    """Файловое вложение сообщения.

    Используйте этот тип для входящих файлов в ``Message.attaches``. Временный
    URL для скачивания можно получить через ``client.get_file_by_id``.

    Example:
        .. code-block:: python

           for attach in message.attaches:
               if isinstance(attach, FileAttachment):
                   file = await client.get_file_by_id(
                       message.chat_id,
                       message.id,
                       attach.file_id,
                   )

    :ivar file_id: ID файла.
    :vartype file_id: int
    :ivar name: Имя файла.
    :vartype name: str
    :ivar size: Размер файла в байтах.
    :vartype size: int
    :ivar token: Токен файла.
    :vartype token: str
    :ivar type: Тип вложения.
    :vartype type: Literal[AttachmentType.FILE]
    """

    file_id: int
    name: str
    size: int
    token: str
    type: Literal[AttachmentType.FILE] = Field(alias="_type")


class FileRequest(CamelModel):
    """Данные для скачивания файлового вложения.

    :ivar unsafe: Помечен ли файл как небезопасный.
    :vartype unsafe: bool
    :ivar url: URL файла.
    :vartype url: str
    """

    unsafe: bool
    url: str
