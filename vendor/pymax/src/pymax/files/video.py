from collections.abc import AsyncGenerator
from pathlib import Path

from .base import BaseFile


class Video(BaseFile):
    """Видео для отправки в сообщение.

    ``Video`` принимает ``path``, ``url`` или ``raw``. При отправке PyMax
    загружает видео чанками и ждет от Max событие готовности обработки.

    Args:
        raw: Байты видео.
        url: URL видео.
        path: Локальный путь к видео.
        name: Имя файла. Обязательно для ``raw``.

    Example:
        .. code-block:: python

           from pymax import Video

           await client.send_message(
               chat_id=123,
               text="Видео",
               attachments=[Video(path="clip.mp4")],
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
        """Читает видео целиком в память.

        Returns:
            Байты видео.
        """
        return await super().read()

    async def size(self) -> int:
        """Возвращает размер видео в байтах.

        Returns:
            Размер видео.
        """
        return await super().size()

    def iter_chunks(self, size: int) -> AsyncGenerator[bytes, None]:
        """Итерирует видео чанками.

        Args:
            size: Размер чанка в байтах.

        Returns:
            Async generator с байтами.
        """
        return super().iter_chunks(size)
