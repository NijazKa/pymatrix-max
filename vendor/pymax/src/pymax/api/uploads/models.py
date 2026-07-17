from pydantic import BaseModel

from pymax.api.models import CamelModel


class PhotoPayloadResponse(BaseModel):
    token: str


class PhotoUploadResponse(BaseModel):
    photos: dict[str, PhotoPayloadResponse]


class VideoPayloadResponse(CamelModel):
    url: str
    video_id: int
    token: str


class VideoUploadResponse(BaseModel):
    info: list[VideoPayloadResponse]


class FilePayloadResponse(CamelModel):
    url: str
    file_id: int
    token: str


class FileUploadResponse(BaseModel):
    info: list[FilePayloadResponse]


# class PhotoUploadResult(CamelModel):
#     type: Literal[AttachmentType.PHOTO] = Field(
#         serialization_alias="_type", default=AttachmentType.PHOTO
#     )
#     photo_token: str


# class VideoUploadResult(CamelModel):
#     type: Literal[AttachmentType.VIDEO] = Field(
#         serialization_alias="_type", default=AttachmentType.VIDEO
#     )
#     video_id: int
#     token: str
