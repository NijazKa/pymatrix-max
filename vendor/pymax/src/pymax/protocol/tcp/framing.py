import struct

from pymax.protocol import PackedPacket, TcpPacketHeader


class TcpPacketFramer:
    HEADER_STRUCT = struct.Struct(">BBHHI")
    HEADER_SIZE = HEADER_STRUCT.size

    def pack(
        self,
        *,
        ver: int,
        cmd: int,
        seq: int,
        opcode: int,
        flags: int,
        payload_bytes: bytes,
    ) -> bytes:
        packed_len = ((flags & 0xFF) << 24) | (len(payload_bytes) & 0x00FFFFFF)
        header = self.HEADER_STRUCT.pack(
            ver,
            cmd,
            seq,
            opcode,
            packed_len,
        )
        return header + payload_bytes

    def unpack(self, data: bytes) -> PackedPacket | None:
        if len(data) < self.HEADER_SIZE:
            return None

        ver, cmd, seq, opcode, packed_len = self.HEADER_STRUCT.unpack_from(data, 0)
        flags = (packed_len >> 24) & 0xFF
        payload_len = packed_len & 0x00FFFFFF

        total_len = self.HEADER_SIZE + payload_len
        if len(data) < total_len:
            return None

        return PackedPacket(
            header=TcpPacketHeader(
                ver=ver,
                cmd=cmd,
                seq=seq,
                opcode=opcode,
                flags=flags,
                payload_len=payload_len,
            ),
            payload_bytes=data[self.HEADER_SIZE : total_len],
        )

    def unpack_header(self, data: bytes) -> int | None:
        if len(data) < self.HEADER_SIZE:
            return None

        _, _, _, _, packed_len = self.HEADER_STRUCT.unpack_from(data, 0)
        payload_len = packed_len & 0x00FFFFFF

        return payload_len
