from __future__ import annotations

from dataclasses import dataclass
import time

from mautrix.types import UserID
from mautrix.util.async_db import Database


@dataclass
class PortalUser:
    """Association between a shared MAX group/channel and a Matrix account.

    Group and channel portals are shared by MAX ``chat_id``. This table keeps
    the per-account side of that relation so every Matrix user whose own MAX
    session can access the chat is invited to the same Matrix room.
    """

    db: Database

    chat_id: str
    mxid: UserID
    created_at: int
    last_seen_at: int

    @classmethod
    def _from_row(cls, row) -> "PortalUser":
        return cls(
            db=cls.db,
            chat_id=row["chat_id"],
            mxid=UserID(row["mxid"]),
            created_at=int(row["created_at"]),
            last_seen_at=int(row["last_seen_at"]),
        )

    @classmethod
    async def add(cls, chat_id: str, mxid: UserID) -> None:
        now = int(time.time())
        await cls.db.execute(
            "INSERT INTO portal_user (chat_id, mxid, created_at, last_seen_at) "
            "VALUES ($1, $2, $3, $3) "
            "ON CONFLICT (chat_id, mxid) DO UPDATE SET "
            "last_seen_at=excluded.last_seen_at",
            str(chat_id),
            mxid,
            now,
        )

    @classmethod
    async def exists(cls, chat_id: str, mxid: UserID) -> bool:
        row = await cls.db.fetchrow(
            "SELECT 1 FROM portal_user WHERE chat_id=$1 AND mxid=$2 LIMIT 1",
            str(chat_id),
            mxid,
        )
        return row is not None

    @classmethod
    async def get_users(cls, chat_id: str) -> list[UserID]:
        rows = await cls.db.fetch(
            "SELECT mxid FROM portal_user WHERE chat_id=$1 ORDER BY created_at, mxid",
            str(chat_id),
        )
        return [UserID(row["mxid"]) for row in rows]

    @classmethod
    async def get_for_user(cls, mxid: UserID) -> list["PortalUser"]:
        rows = await cls.db.fetch(
            "SELECT chat_id, mxid, created_at, last_seen_at FROM portal_user "
            "WHERE mxid=$1 ORDER BY last_seen_at DESC",
            mxid,
        )
        return [cls._from_row(row) for row in rows]

    @classmethod
    async def remove(cls, chat_id: str, mxid: UserID) -> bool:
        existed = await cls.exists(chat_id, mxid)
        await cls.db.execute(
            "DELETE FROM portal_user WHERE chat_id=$1 AND mxid=$2",
            str(chat_id),
            mxid,
        )
        return existed

    @classmethod
    async def delete_by_chat(cls, chat_id: str) -> None:
        await cls.db.execute(
            "DELETE FROM portal_user WHERE chat_id=$1",
            str(chat_id),
        )
