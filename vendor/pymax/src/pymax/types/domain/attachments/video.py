from typing import Any, ClassVar, Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from pymax.types.domain.base import CamelModel

from .enums import AttachmentType


class VideoAttachment(CamelModel):
    """Видео-вложение сообщения.

    Используйте этот тип для входящих видео в ``Message.attaches``. Временный
    URL для просмотра можно получить через ``client.get_video_by_id``.

    Example:
        .. code-block:: python

           for attach in message.attaches:
               if isinstance(attach, VideoAttachment):
                   video = await client.get_video_by_id(
                       message.chat_id,
                       message.id,
                       attach.video_id,
                   )

    :ivar height: Высота видео.
    :vartype height: int
    :ivar width: Ширина видео.
    :vartype width: int
    :ivar video_id: ID видео.
    :vartype video_id: int
    :ivar duration: Длительность видео.
    :vartype duration: int | None
    :ivar preview_data: Данные превью.
    :vartype preview_data: bytes
    :ivar type: Тип вложения.
    :vartype type: Literal[AttachmentType.VIDEO]
    :ivar thumbnail: URL миниатюры.
    :vartype thumbnail: str
    :ivar token: Токен видео.
    :vartype token: str
    :ivar video_type: Код типа видео в Max.
    :vartype video_type: int
    """

    height: int
    width: int
    video_id: int
    duration: int | None = None
    preview_data: bytes
    type: Literal[AttachmentType.VIDEO] = Field(alias="_type")
    thumbnail: str
    token: str
    video_type: int


class VideoRequest(CamelModel):
    """Данные для просмотра видео-вложения.

    MAX может вернуть URL обычной строкой или динамической парой
    ``путь -> список CDN-хостов``. Служебное поле ``FAILOVER_HOSTS`` также
    содержит список хостов и не является путём к видео.

    :ivar external: Признак или URL внешнего источника видео.
    :vartype external: str | bool | None
    :ivar cache: Использовать ли кеш.
    :vartype cache: bool
    :ivar url: URL видео.
    :vartype url: str
    """

    external: str | bool | None = Field(default=None, alias="EXTERNAL")
    cache: bool
    url: str

    _RESERVED_KEYS: ClassVar[frozenset[str]] = frozenset({
        "EXTERNAL",
        "CACHE",
        "FAILOVER_HOSTS",
        "HOSTS",
        "CDN_HOSTS",
    })

    @staticmethod
    def _first_string(value: Any) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        if isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
        return None

    @staticmethod
    def _is_absolute_url(value: str) -> bool:
        parsed = urlsplit(value)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        return (
            value.startswith("/")
            or value.startswith("?")
            or value.startswith("//")
            or VideoRequest._is_absolute_url(value)
        )

    @classmethod
    def _normalise_host(cls, value: Any) -> str | None:
        host = cls._first_string(value)
        if host is None:
            return None

        parsed = urlsplit(host if "://" in host else f"https://{host}")
        if not parsed.netloc:
            return None
        return f"{parsed.scheme or 'https'}://{parsed.netloc}"

    @classmethod
    def _build_url(cls, path_or_url: str, hosts: Any) -> str | None:
        path_or_url = path_or_url.strip()
        if not path_or_url:
            return None
        if cls._is_absolute_url(path_or_url):
            return path_or_url
        if path_or_url.startswith("//"):
            return "https:" + path_or_url

        base = cls._normalise_host(hosts)
        if base is None:
            return None

        if path_or_url.startswith("?"):
            return base + "/" + path_or_url
        if not path_or_url.startswith("/"):
            path_or_url = "/" + path_or_url
        return base + path_or_url

    @classmethod
    def _url_from_value(cls, value: Any) -> str | None:
        candidate = cls._first_string(value)
        if candidate is None:
            return None
        if cls._is_absolute_url(candidate):
            return candidate
        if candidate.startswith("//"):
            return "https:" + candidate
        return None

    @model_validator(mode="before")
    @classmethod
    def unwrap_dynamic_url(cls, value: Any) -> Any:
        """Нормализовать URL и не принимать ``FAILOVER_HOSTS`` за путь."""
        if not isinstance(value, dict):
            return value

        failover_hosts = value.get("FAILOVER_HOSTS")

        # Обычный формат: url содержит абсолютный URL или относительный путь.
        if "url" in value:
            direct = cls._first_string(value.get("url"))
            if direct is not None:
                url = cls._url_from_value(direct)
                if url is None and cls._looks_like_path(direct):
                    url = cls._build_url(direct, failover_hosts)
                if url is not None:
                    return {**value, "url": url}

        # Формат MAX: ключ — путь к видео, значение — список CDN-хостов.
        # Сначала рассматриваем только ключи, явно похожие на путь/URL.
        for key, raw_value in value.items():
            key_text = str(key).strip()
            if key_text.upper() in cls._RESERVED_KEYS:
                continue
            if not cls._looks_like_path(key_text):
                continue

            if cls._is_absolute_url(key_text):
                return {**value, "url": key_text}
            if key_text.startswith("//"):
                return {**value, "url": "https:" + key_text}

            url = cls._build_url(key_text, raw_value)
            if url is None:
                url = cls._build_url(key_text, failover_hosts)
            if url is not None:
                return {**value, "url": url}

        # Редкий вариант: абсолютный URL лежит в значении неизвестного поля.
        for key, raw_value in value.items():
            if str(key).strip().upper() in cls._RESERVED_KEYS:
                continue
            url = cls._url_from_value(raw_value)
            if url is not None:
                return {**value, "url": url}

        return value
