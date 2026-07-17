from collections.abc import AsyncGenerator
from pathlib import Path

from .base import BaseFile


class File(BaseFile):
    """Обычный файл для отправки в сообщение.

    Используйте ``File`` в ``attachments`` у ``send_message``, ``Message.answer``
    или ``Chat.answer``. Источником может быть ``path``, ``url`` или ``raw``;
    передавайте только один источник. Для ``raw`` обязательно укажите ``name``.

    Args:
        raw: Байты файла.
        url: URL, откуда PyMax скачает файл перед upload.
        path: Локальный путь к файлу.
        name: Имя файла, которое будет отправлено Max.

    Example:
        .. code-block:: python

           from pymax import File

           await client.send_message(
               chat_id=123,
               text="Документ",
               attachments=[File(path="report.pdf")],
           )
    """

    def __init__(
        self,
        raw: bytes | None = None,
        *,
        url: str | None = None,
        path: str | None = None,
        name: str | None = None,
    ) -> None:
        self.name: str = name or ""
        if not self.name and path:
            self.name = Path(path).name
        elif not self.name and url:
            self.name = Path(url).name

        if not self.name:
            raise ValueError("Either name, url or path must be provided.")

        super().__init__(raw=raw, url=url, path=path, name=self.name)

    async def read(self) -> bytes:
        """Читает файл целиком в память.

        Returns:
            Байты файла.
        """
        return await super().read()

    async def size(self) -> int:
        """Возвращает размер файла в байтах.

        Returns:
            Размер файла.
        """
        return await super().size()

    def iter_chunks(self, size: int) -> AsyncGenerator[bytes, None]:
        """Итерирует файл чанками.

        Args:
            size: Размер чанка в байтах.

        Returns:
            Async generator с байтами.
        """
        return super().iter_chunks(size)
