from __future__ import annotations

from typing import TYPE_CHECKING

from pymax.logging import get_logger
from pymax.protocol import Opcode

from .enums import DeviceType
from .payloads import (
    MobileHandshakePayload,
    MobileUserAgentPayload,
    WebHandshakePayload,
)

if TYPE_CHECKING:
    from pymax.app import App


logger = get_logger(__name__)


class SessionService:
    def __init__(self, app: App) -> None:
        self.app = app

    async def handshake(
        self,
        mt_instance_id: str,
        user_agent: MobileUserAgentPayload,
        device_id: str,
    ) -> None:
        if user_agent.device_type == DeviceType.WEB:
            await self.web_handshake(user_agent, device_id)
            return

        await self.mobile_handshake(mt_instance_id, user_agent, device_id)

    async def mobile_handshake(
        self,
        mt_instance_id: str,
        user_agent: MobileUserAgentPayload,
        device_id: str,
    ) -> None:
        logger.debug(
            "mobile handshake mt_instance_id_set=%s device_id=%s app_version=%s",
            bool(mt_instance_id),
            device_id,
            user_agent.app_version,
        )
        frame = MobileHandshakePayload(
            mt_instanceid=mt_instance_id,
            user_agent=user_agent,
            device_id=device_id,
        )
        await self.app.invoke(Opcode.SESSION_INIT, frame.to_payload())
        logger.info("mobile handshake completed")

    async def web_handshake(self, user_agent: MobileUserAgentPayload, device_id: str) -> None:
        logger.debug(
            "web handshake device_id=%s app_version=%s browser=%s",
            device_id,
            user_agent.app_version,
            user_agent.device_name,
        )
        frame = WebHandshakePayload(
            user_agent=user_agent,
            device_id=device_id,
        )
        await self.app.invoke(Opcode.SESSION_INIT, frame.to_payload())
        logger.info("web handshake completed")
