import json

from pydantic import ValidationError

from pymax.logging import get_logger
from pymax.protocol import InboundFrame, OutboundFrame
from pymax.protocol.base import BaseProtocol

logger = get_logger(__name__)


class WsProtocol(BaseProtocol):
    version = 11

    def encode(self, frame: OutboundFrame) -> str:
        return frame.model_dump_json()

    def decode(self, raw: bytes | str) -> InboundFrame:
        try:
            data = json.loads(raw)
            return InboundFrame.model_validate(data)
        except json.JSONDecodeError:
            logger.debug("failed to decode websocket frame json", exc_info=True)
            return InboundFrame(opcode=0, cmd=0, seq=None, payload=None, raw=None)
        except ValidationError:
            logger.debug("failed to validate websocket frame", exc_info=True)
            return InboundFrame(opcode=0, cmd=0, seq=None, payload=None, raw=None)
