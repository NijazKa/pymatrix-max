from enum import Enum


class DeviceType(str, Enum):
    """Тип устройства, который отправляется в handshake и login."""

    WEB = "WEB"
    ANDROID = "ANDROID"
    IOS = "IOS"
    DESKTOP = "DESKTOP"
