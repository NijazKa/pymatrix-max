import mimetypes
from collections.abc import AsyncGenerator
from pathlib import Path
from urllib.parse import urlsplit

from .base import BaseFile
from .static import ALLOWED_EXTENSIONS


class Photo(BaseFile):
    """Фото для отправки в сообщение.

    ``Photo`` принимает ``path``, ``url`` или ``raw`` и проверяет расширение:
    ``.jpg``, ``.jpeg``, ``.png``, ``.gif``, ``.webp`` или ``.bmp``.

    Args:
        raw: Байты изображения.
        url: URL изображения.
        path: Локальный путь к изображению.
        name: Имя файла. Обязательно для ``raw``.

    Example:
        .. code-block:: python

           from pymax import Photo

           await client.send_message(
               chat_id=123,
               text="Фото",
               attachments=[Photo(path="image.jpg")],
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
        if path:
            self.file_name = Path(path).name
        elif url:
            self.file_name = Path(url).name
        elif name:
            self.file_name = name
        else:
            self.file_name = ""

        super().__init__(raw=raw, url=url, path=path, name=name)

    def validate_photo(self) -> tuple[str, str] | None:
        """Проверяет расширение и MIME-тип фото.

        Returns:
            ``(extension, mime_type)`` или ``None``, если источник не задан.

        Raises:
            ValueError: Если расширение или MIME-тип не похожи на изображение.
        """
        if self.path or self.raw is not None:
            source_name = self.path or self.file_name
            extension = Path(source_name).suffix.lower()
            if extension not in ALLOWED_EXTENSIONS:
                msg = f"Invalid photo extension: {extension}. Allowed: {ALLOWED_EXTENSIONS}"
                raise ValueError(msg)
            return (extension[1:], ("image/" + extension[1:]).lower())
        if self.url:
            url_path = urlsplit(self.url).path
            extension = Path(url_path).suffix.lower()
            if extension not in ALLOWED_EXTENSIONS:
                msg = f"Invalid photo extension: {extension}. Allowed: {ALLOWED_EXTENSIONS}"
                raise ValueError(msg)

            mime_type = mimetypes.guess_type(url_path)[0]

            if not mime_type or not mime_type.startswith("image/"):
                msg = f"URL does not appear to be an image: {self.url}"
                raise ValueError(msg)

            return (extension[1:], mime_type)
        return None

    async def read(self) -> bytes:
        """Читает фото целиком в память.

        Returns:
            Байты изображения.
        """
        return await super().read()

    async def size(self) -> int:
        """Возвращает размер фото в байтах.

        Returns:
            Размер изображения.
        """
        return await super().size()

    def iter_chunks(self, size: int) -> AsyncGenerator[bytes, None]:
        """Итерирует фото чанками.

        Args:
            size: Размер чанка в байтах.

        Returns:
            Async generator с байтами.
        """
        return super().iter_chunks(size)
