import asyncio
from asyncio import Future

from pymax.protocol import InboundFrame


class PendingRequests:
    def __init__(self) -> None:
        self._pending: dict[int, Future[InboundFrame]] = {}

    def create(self, seq: int) -> Future[InboundFrame]:
        future = asyncio.get_running_loop().create_future()
        self._pending[seq] = future
        return future

    def resolve(self, seq: int, frame: InboundFrame) -> bool:
        future = self._pending.pop(seq, None)
        if future is None:
            return False

        if not future.done():
            future.set_result(frame)
        return True

    def reject(self, seq: int, exc: Exception) -> bool:
        future = self._pending.pop(seq, None)
        if future is None:
            return False

        if not future.done():
            future.set_exception(exc)
        return True

    def discard(self, seq: int) -> None:
        future = self._pending.pop(seq, None)
        if future and not future.done():
            future.cancel()

    def cancel_all(self, exc: Exception | None = None) -> None:
        for future in self._pending.values():
            if not future.done():
                if exc:
                    future.set_exception(exc)
                else:
                    future.cancel()
        self._pending.clear()
