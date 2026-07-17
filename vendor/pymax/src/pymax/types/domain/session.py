from typing import Any

from .base import CamelModel


class Session(CamelModel):
    """Активная сессия аккаунта.

    :ivar id: ID сессии.
    :vartype id: int | str | None
    :ivar device_id: ID устройства.
    :vartype device_id: str | None
    :ivar current: Является ли сессия текущей.
    :vartype current: bool | None
    :ivar user_agent: User-Agent сессии.
    :vartype user_agent: str | None
    :ivar app_version: Версия приложения.
    :vartype app_version: str | None
    :ivar device_name: Название устройства.
    :vartype device_name: str | None
    :ivar device_type: Тип устройства.
    :vartype device_type: str | None
    :ivar platform: Платформа устройства.
    :vartype platform: str | None
    :ivar ip: IP-адрес сессии.
    :vartype ip: str | None
    :ivar location: Локация сессии.
    :vartype location: str | None
    :ivar created: Время создания в формате Unix time.
    :vartype created: int | None
    :ivar updated: Время обновления в формате Unix time.
    :vartype updated: int | None
    :ivar last_activity: Время последней активности в формате Unix time.
    :vartype last_activity: int | None
    :ivar options: Дополнительные параметры сессии от Max.
    :vartype options: dict[str, Any] | list[Any] | None
    """

    id: int | str | None = None
    device_id: str | None = None
    current: bool | None = None
    user_agent: str | None = None
    app_version: str | None = None
    device_name: str | None = None
    device_type: str | None = None
    platform: str | None = None
    ip: str | None = None
    location: str | None = None
    created: int | None = None
    updated: int | None = None
    last_activity: int | None = None
    options: dict[str, Any] | list[Any] | None = None
