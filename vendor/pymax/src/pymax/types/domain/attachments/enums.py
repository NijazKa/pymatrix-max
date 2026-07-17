from enum import Enum


class AttachmentType(str, Enum):
    """Тип вложения сообщения."""

    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
    FILE = "FILE"
    STICKER = "STICKER"
    AUDIO = "AUDIO"
    CONTROL = "CONTROL"
    CONTACT = "CONTACT"
    CALL = "CALL"
    SHARE = "SHARE"
    INLINE_KEYBOARD = "INLINE_KEYBOARD"
    UNKNOWN = "UNKNOWN"


class TranscriptionStatus(str, Enum):
    """Статус транскрибации аудио."""

    FAILED = "FAILED"
    MEDIA_NOT_READY = "MEDIA_NOT_READY"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    UNKNOWN = "UNKNOWN"
