import os
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

import aiofiles
import aiohttp


class BaseFile(ABC):
    def __init__(
        self,
        raw: bytes | None = None,
        *,
        path: str | None,
        url: str | None,
        name: str | None,
    ) -> None:
        self.path = path
        self.url = url
        self.raw = raw
        self.name = name

        if raw is None and not url and not path:
            raise ValueError("Path or Url or Raw must be provided")

        if raw is not None and not name:
            raise ValueError("Name must be provided for raw data")

        sources = sum(source is not None for source in (raw, url, path))
        if sources > 1:
            raise ValueError("Only one of raw, url or path must be provided.")

    @abstractmethod
    async def read(self) -> bytes:
        if self.raw:
            return self.raw

        if self.path:
            async with aiofiles.open(self.path, "rb") as f:
                return await f.read()
        elif self.url:
            async with aiohttp.ClientSession() as session:  # noqa: SIM117
                async with session.get(self.url) as resp:
                    resp.raise_for_status()
                    return await resp.read()
        else:
            raise ValueError("Path or Url must be provided")

    @abstractmethod
    async def size(self) -> int:
        if self.raw:
            return len(self.raw)

        if self.path:
            return os.path.getsize(self.path)

        if self.url:
            async with aiohttp.ClientSession() as session:  # noqa: SIM117
                async with session.head(self.url) as resp:
                    return int(resp.headers["Content-Length"])
        else:
            raise ValueError("Path or Url must be provided")

    @abstractmethod
    async def iter_chunks(self, size: int) -> AsyncGenerator[bytes, None]:
        if size <= 0:
            raise ValueError("size must be greater than zero")

        if self.raw:
            for i in range(0, len(self.raw), size):
                yield self.raw[i : i + size]

        if self.path:
            async with aiofiles.open(self.path, "rb") as f:
                while True:
                    data = await f.read(size)

                    if not data:
                        break
                    yield data

        if self.url:
            async with aiohttp.ClientSession() as session:  # noqa: SIM117
                async with session.get(self.url) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.content.iter_chunked(size):
                        yield chunk
