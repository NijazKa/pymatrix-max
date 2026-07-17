from __future__ import annotations

from dataclasses import dataclass
import time

from mautrix.types import UserID
from mautrix.util.async_db import Database


@dataclass
class BlockedChat:
    """A MAX group/channel that a Matrix user does not want bridged.

    This is a bridge-local denylist. MAX has no exposed API for preventing a
    specific group from inviting an account again, so when a blocked chat
    produces a push event the bridge immediately leaves it again.
    """

    db: Database

    mxid: UserID
    chat_id: str
    name: str | None = None
    created_at: int = 0

    @classmethod
    def _from_row(cls, row) -> "BlockedChat":
        return cls(
            db=cls.db,
            mxid=UserID(row["mxid"]),
            chat_id=row["chat_id"],
            name=row["name"],
            created_at=int(row["created_at"]),
        )

    @classmethod
    async def is_blocked(cls, mxid: UserID, chat_id: str) -> bool:
        row = await cls.db.fetchrow(
            "SELECT 1 FROM blocked_chat WHERE mxid=$1 AND chat_id=$2 LIMIT 1",
            mxid,
            chat_id,
        )
        return row is not None

    @classmethod
    async def get_all(cls, mxid: UserID) -> list["BlockedChat"]:
        rows = await cls.db.fetch(
            "SELECT mxid, chat_id, name, created_at FROM blocked_chat "
            "WHERE mxid=$1 ORDER BY created_at DESC",
            mxid,
        )
        return [cls._from_row(row) for row in rows]

    @classmethod
    async def add(
        cls,
        mxid: UserID,
        chat_id: str,
        name: str | None = None,
    ) -> None:
        await cls.db.execute(
            "INSERT INTO blocked_chat (mxid, chat_id, name, created_at) "
            "VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (mxid, chat_id) DO UPDATE SET "
            "name=excluded.name, created_at=excluded.created_at",
            mxid,
            chat_id,
            name,
            int(time.time()),
        )

    @classmethod
    async def remove(cls, mxid: UserID, chat_id: str) -> bool:
        existed = await cls.is_blocked(mxid, chat_id)
        await cls.db.execute(
            "DELETE FROM blocked_chat WHERE mxid=$1 AND chat_id=$2",
            mxid,
            chat_id,
        )
        return existed
