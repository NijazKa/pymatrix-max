from __future__ import annotations

from dataclasses import dataclass

from mautrix.types import UserID
from mautrix.util.async_db import Database


@dataclass
class Puppet:
    db: Database

    max_user_id: str
    mxid: UserID
    name: str | None
    phone: str | None
    avatar_url: str | None
    custom_mxid: UserID | None  # для double puppeting: чей это реальный Matrix-аккаунт

    @classmethod
    async def get_by_max_id(cls, max_user_id: str) -> "Puppet | None":
        row = await cls.db.fetchrow(
            "SELECT max_user_id, mxid, name, phone, avatar_url, custom_mxid "
            "FROM puppet WHERE max_user_id=$1",
            max_user_id,
        )
        return cls._from_row(row) if row else None

    @classmethod
    async def get_by_custom_mxid(cls, mxid: UserID) -> "Puppet | None":
        row = await cls.db.fetchrow(
            "SELECT max_user_id, mxid, name, phone, avatar_url, custom_mxid "
            "FROM puppet WHERE custom_mxid=$1",
            mxid,
        )
        return cls._from_row(row) if row else None

    @classmethod
    def _from_row(cls, row) -> "Puppet":
        return cls(
            db=cls.db,
            max_user_id=row["max_user_id"],
            mxid=row["mxid"],
            name=row["name"],
            phone=row["phone"],
            avatar_url=row["avatar_url"],
            custom_mxid=row["custom_mxid"],
        )

    async def insert(self) -> None:
        await self.db.execute(
            "INSERT INTO puppet "
            "(max_user_id, mxid, name, phone, avatar_url, custom_mxid) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            self.max_user_id,
            self.mxid,
            self.name,
            self.phone,
            self.avatar_url,
            self.custom_mxid,
        )

    async def save(self) -> None:
        await self.db.execute(
            "UPDATE puppet SET name=$2, phone=$3, avatar_url=$4, custom_mxid=$5 "
            "WHERE max_user_id=$1",
            self.max_user_id,
            self.name,
            self.phone,
            self.avatar_url,
            self.custom_mxid,
        )
