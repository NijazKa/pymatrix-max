from abc import ABC, abstractmethod

from .models import InboundFrame, OutboundFrame


class BaseProtocol(ABC):
    version: int

    @abstractmethod
    def encode(self, frame: OutboundFrame) -> bytes | str: ...

    @abstractmethod
    def decode(self, raw: bytes | str) -> InboundFrame: ...
