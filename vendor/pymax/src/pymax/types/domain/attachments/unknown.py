from typing import Any

from pydantic import Field, model_validator

from pymax.types.domain.base import CamelModel

from .enums import AttachmentType

KNOWN_ATTACHMENT_TYPES = {
    attachment_type.value
    for attachment_type in AttachmentType
    if attachment_type != AttachmentType.UNKNOWN
}


class UnknownAttachment(CamelModel):
    """Вложение неизвестного типа.

    :ivar type: Тип вложения.
    :vartype type: str
    """

    type: str = Field(alias="_type")

    @model_validator(mode="before")
    @classmethod
    def reject_known_attachment_type(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        attachment_type = value.get("_type", value.get("type"))
        if attachment_type in KNOWN_ATTACHMENT_TYPES:
            raise ValueError("Known attachment type should be parsed by its own model")

        return value
