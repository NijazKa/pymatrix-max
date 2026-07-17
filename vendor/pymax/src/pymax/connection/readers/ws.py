from pymax.logging import get_logger
from pymax.transport.websocket import WebSocketTransport

from .base import BaseReader

logger = get_logger(__name__)


class WSReader(BaseReader):
    def __init__(self, transport: WebSocketTransport) -> None:
        self.transport = transport

    async def read(self) -> bytes | str:
        return await self.transport.recv()
