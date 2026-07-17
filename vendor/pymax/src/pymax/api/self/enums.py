from enum import Enum


class AvatarType(str, Enum):
    USER_AVATAR = "USER_AVATAR"


class SelfPayloadKey(str, Enum):
    PROFILE = "profile"
    URL = "url"
    TOKEN = "token"
