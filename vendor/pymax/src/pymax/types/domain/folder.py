from typing import Any

from pydantic import Field

from .base import CamelModel


class Folder(CamelModel):
    """Папка чатов.

    :ivar source_id: ID источника папки в Max.
    :vartype source_id: int
    :ivar include: ID чатов, включенных в папку.
    :vartype include: list[int]
    :ivar options: Дополнительные настройки папки.
    :vartype options: list[Any]
    :ivar update_time: Время обновления в формате Unix time.
    :vartype update_time: int
    :ivar id: ID папки.
    :vartype id: str
    :ivar filters: Фильтры папки.
    :vartype filters: list[Any]
    :ivar title: Название папки.
    :vartype title: str
    """

    source_id: int = 0
    include: list[int] = Field(default_factory=list)
    options: list[Any] = Field(default_factory=list)
    update_time: int = 0
    id: str = ""
    filters: list[Any] = Field(default_factory=list)
    title: str = ""


class FolderUpdate(CamelModel):
    """Обновление папки чатов.

    :ivar folders_order: Порядок папок.
    :vartype folders_order: list[str]
    :ivar folder: Обновленная папка.
    :vartype folder: Folder | None
    :ivar folder_sync: Метка синхронизации папок.
    :vartype folder_sync: int
    """

    folders_order: list[str] = Field(default_factory=list)
    folder: Folder | None = None
    folder_sync: int = 0


class FolderList(CamelModel):
    """Список папок чатов.

    :ivar folders_order: Порядок папок.
    :vartype folders_order: list[str]
    :ivar folders: Папки чатов.
    :vartype folders: list[Folder]
    :ivar all_filter_exclude_folders: Папки, исключенные общими фильтрами.
    :vartype all_filter_exclude_folders: list[Any]
    :ivar folder_sync: Метка синхронизации папок.
    :vartype folder_sync: int
    """

    folders_order: list[str] = Field(default_factory=list)
    folders: list[Folder] = Field(default_factory=list)
    all_filter_exclude_folders: list[Any] = Field(default_factory=list)
    folder_sync: int = 0
