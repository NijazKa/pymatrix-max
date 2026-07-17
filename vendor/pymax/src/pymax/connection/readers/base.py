from abc import ABC, abstractmethod


class BaseReader(ABC):
    @abstractmethod
    async def read(self) -> bytes | str: ...
