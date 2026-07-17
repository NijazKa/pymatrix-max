from io import BytesIO

import zstandard


class Lz4BlockCompression:
    def decompress(self, src: bytes, max_output: int = 5 * 1024 * 1024) -> bytes:
        dst = bytearray()
        pos = 0

        while pos < len(src):
            token = src[pos]
            pos += 1

            lit_len = token >> 4
            if lit_len == 15:
                while pos < len(src):
                    b = src[pos]
                    pos += 1
                    lit_len += b
                    if b != 255:
                        break

            if lit_len > 0:
                if pos + lit_len > len(src):
                    raise ValueError("LZ4: literal length out of bounds")
                dst.extend(src[pos : pos + lit_len])
                pos += lit_len
                if len(dst) > max_output:
                    raise ValueError("LZ4: output too large")

            if pos >= len(src):
                break

            if pos + 1 >= len(src):
                raise ValueError("LZ4: incomplete offset")

            offset = src[pos] | (src[pos + 1] << 8)
            pos += 2

            if offset == 0:
                raise ValueError("LZ4: zero offset")

            match_len = (token & 0x0F) + 4
            if (token & 0x0F) == 0x0F:
                while pos < len(src):
                    b = src[pos]
                    pos += 1
                    match_len += b
                    if b != 255:
                        break

            match_pos = len(dst) - offset
            if match_pos < 0:
                raise ValueError("LZ4: match out of bounds")

            for i in range(match_len):
                dst.append(dst[match_pos + (i % offset)])

            if len(dst) > max_output:
                raise ValueError("LZ4: output too large")

        return bytes(dst)

    def compress(self, src: bytes) -> bytes:
        dst = bytearray()
        pos = 0

        while pos < len(src):
            lit_start = pos
            while pos < len(src) and (pos - lit_start) < 15:
                pos += 1

            lit_len = pos - lit_start
            token = (lit_len << 4) & 0xF0

            match_offset = 0
            match_len = 0

            for i in range(max(0, lit_start - 65535), lit_start):
                j = i
                k = lit_start
                while j < i + 65535 and k < len(src) and src[j] == src[k]:
                    j += 1
                    k += 1
                if j - i > match_len:
                    match_offset = lit_start - i
                    match_len = j - i

            if match_len >= 4:
                token |= (match_len - 4) & 0x0F
                dst.append(token)
                dst.extend(src[lit_start : lit_start + lit_len])
                dst.append(match_offset & 0xFF)
                dst.append((match_offset >> 8) & 0xFF)
                pos += match_len
            else:
                token |= lit_len & 0x0F
                dst.append(token)
                dst.extend(src[lit_start : lit_start + lit_len])

        return bytes(dst)


class ZstdCompression:
    def decompress(self, src: bytes, max_output: int = 5 * 1024 * 1024) -> bytes:
        try:
            with zstandard.ZstdDecompressor().stream_reader(BytesIO(src)) as reader:
                result = reader.read(max_output + 1)
        except zstandard.ZstdError as e:
            raise ValueError("Zstd: failed to decompress payload") from e

        if len(result) > max_output:
            raise ValueError("Zstd: output too large")
        return result
