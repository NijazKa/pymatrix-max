from pymax.logging import get_logger
from pymax.protocol.tcp.framing import TcpPacketFramer
from pymax.transport.tcp import TCPTransport

from .base import BaseReader

logger = get_logger(__name__)


class TCPReader(BaseReader):
    def __init__(self, transport: TCPTransport, framer: TcpPacketFramer) -> None:
        super().__init__()
        self.transport = transport
        self.framer = framer

    async def read(self) -> bytes:
        header_bytes = await self.transport.recv(self.framer.HEADER_SIZE)
        payload_len = self.framer.unpack_header(header_bytes)
        if payload_len is None:
            logger.warning(
                "failed to unpack tcp packet header bytes=%s",
                len(header_bytes),
            )
            raise ValueError("Failed to unpack TCP packet header")

        logger.debug("tcp packet header read payload_len=%s", payload_len)
        payload_bytes = await self.transport.recv(payload_len)
        logger.debug("tcp packet payload read bytes=%s", len(payload_bytes))
        return header_bytes + payload_bytes
