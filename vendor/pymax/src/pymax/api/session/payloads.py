from random import randint

from pydantic import Field

from pymax.api.models import CamelModel

from .enums import DeviceType

DEFAULT_WEB_HEADER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
WEB_USER_AGENT_ALIASES = (
    "deviceType",
    "locale",
    "deviceLocale",
    "osVersion",
    "deviceName",
    "headerUserAgent",
    "appVersion",
    "screen",
    "timezone",
)


class MobileUserAgentPayload(CamelModel):
    """User-agent payload, который PyMax отправляет в Max.

    Обычно его создает ``ExtraConfig.generate_user_agent()`` или
    ``ExtraConfig.generate_web_user_agent()``. Передавайте собственный объект
    в ``ExtraConfig(user_agent=...)`` только если нужно явно управлять
    device/app параметрами.
    """

    device_type: DeviceType
    app_version: str
    os_version: str
    timezone: str
    screen: str
    push_device_type: str | None = None
    arch: str | None = None
    locale: str
    build_number: int | None = None
    device_name: str
    device_locale: str
    release: int | None = None
    header_user_agent: str | None = None

    def to_web_payload(self) -> dict:
        """Возвращает payload в формате, который ожидает web-login."""
        payload = self.model_dump(
            by_alias=True,
            exclude_none=True,
        )
        if self.device_type == DeviceType.WEB and "headerUserAgent" not in payload:
            payload["headerUserAgent"] = DEFAULT_WEB_HEADER_USER_AGENT

        return {alias: payload[alias] for alias in WEB_USER_AGENT_ALIASES if alias in payload}


class MobileHandshakePayload(CamelModel):
    mt_instance_id: str = Field(..., alias="mt_instanceid")
    user_agent: MobileUserAgentPayload
    client_session_id: int = Field(default_factory=lambda: randint(1, 70))
    device_id: str


class WebHandshakePayload(CamelModel):
    user_agent: MobileUserAgentPayload
    device_id: str

    def to_payload(self) -> dict:
        return {
            "userAgent": self.user_agent.to_web_payload(),
            "deviceId": self.device_id,
        }
