from typing import Any

from pymax.api.models import CamelModel

from .enums import AvatarType


class UploadPayload(CamelModel):
    count: int = 1
    profile: bool = False


class ChangeProfilePayload(CamelModel):
    first_name: str
    last_name: str | None = None
    description: str | None = None
    photo_token: str | None = None
    avatar_type: AvatarType = AvatarType.USER_AVATAR


class CreateFolderPayload(CamelModel):
    id: str
    title: str
    include: list[int]
    filters: list[Any]


class GetFolderPayload(CamelModel):
    folder_sync: int = 0


class UpdateFolderPayload(CamelModel):
    id: str
    title: str
    include: list[int]
    filters: list[Any]
    options: list[Any]


class DeleteFolderPayload(CamelModel):
    folder_ids: list[str]
