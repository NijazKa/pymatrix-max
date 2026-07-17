from __future__ import annotations

from dataclasses import dataclass

from mautrix.types import RoomID, UserID
from mautrix.util.async_db import Database


@dataclass
class Portal:
    db: Database

    chat_id: str
    receiver: UserID | None
    mxid: RoomID | None
    name: str | None
    is_direct: bool
    remote_user_id: str | None = None

    @classmethod
    async def get_by_chat_id(cls, chat_id: str, receiver: UserID | None) -> "Portal | None":
        row = await cls.db.fetchrow(
            "SELECT chat_id, receiver, mxid, name, is_direct, remote_user_id "
            "FROM portal WHERE chat_id=$1 AND receiver IS NOT DISTINCT FROM $2",
            chat_id,
            receiver,
        )
        return cls._from_row(row) if row else None

    @classmethod
    async def get_by_mxid(cls, mxid: RoomID) -> "Portal | None":
        row = await cls.db.fetchrow(
            "SELECT chat_id, receiver, mxid, name, is_direct, remote_user_id "
            "FROM portal WHERE mxid=$1",
            mxid,
        )
        return cls._from_row(row) if row else None

    @classmethod
    def _from_row(cls, row) -> "Portal":
        return cls(
            db=cls.db,
            chat_id=row["chat_id"],
            receiver=row["receiver"],
            mxid=row["mxid"],
            name=row["name"],
            is_direct=bool(row["is_direct"]),
            remote_user_id=row["remote_user_id"],
        )

    async def insert(self) -> None:
        await self.db.execute(
            "INSERT INTO portal "
            "(chat_id, receiver, mxid, name, is_direct, remote_user_id) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            self.chat_id,
            self.receiver,
            self.mxid,
            self.name,
            self.is_direct,
            self.remote_user_id,
        )

    async def save(self) -> None:
        await self.db.execute(
            "UPDATE portal SET mxid=$3, name=$4, is_direct=$5, remote_user_id=$6 "
            "WHERE chat_id=$1 AND receiver IS NOT DISTINCT FROM $2",
            self.chat_id,
            self.receiver,
            self.mxid,
            self.name,
            self.is_direct,
            self.remote_user_id,
        )

    async def delete(self) -> None:
        await self.db.execute(
            "DELETE FROM portal WHERE chat_id=$1 AND receiver IS NOT DISTINCT FROM $2",
            self.chat_id,
            self.receiver,
        )
