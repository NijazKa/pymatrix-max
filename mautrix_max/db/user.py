from __future__ import annotations

from dataclasses import dataclass

from mautrix.types import RoomID, UserID
from mautrix.util.async_db import Database

fake_db = Database.create("") if False else None  # для типизации в редакторах


@dataclass
class User:
    db: Database

    mxid: UserID
    max_phone: str | None
    max_session_file: str | None
    management_room: RoomID | None

    @classmethod
    async def get_by_mxid(cls, mxid: UserID) -> "User | None":
        row = await cls.db.fetchrow(
            "SELECT mxid, max_phone, max_session_file, management_room "
            'FROM "user" WHERE mxid=$1',
            mxid,
        )
        return cls._from_row(row) if row else None

    @classmethod
    async def all_logged_in(cls) -> list["User"]:
        rows = await cls.db.fetch(
            "SELECT mxid, max_phone, max_session_file, management_room "
            'FROM "user" WHERE max_phone IS NOT NULL'
        )
        return [cls._from_row(row) for row in rows]

    @classmethod
    def _from_row(cls, row) -> "User":
        return cls(
            db=cls.db,
            mxid=UserID(row["mxid"]),
            max_phone=row["max_phone"],
            max_session_file=row["max_session_file"],
            management_room=(
                RoomID(row["management_room"]) if row["management_room"] else None
            ),
        )

    async def insert(self) -> None:
        await self.db.execute(
            'INSERT INTO "user" '
            "(mxid, max_phone, max_session_file, management_room) "
            "VALUES ($1, $2, $3, $4)",
            self.mxid,
            self.max_phone,
            self.max_session_file,
            self.management_room,
        )

    async def save(self) -> None:
        await self.db.execute(
            'UPDATE "user" SET max_phone=$2, max_session_file=$3, '
            "management_room=$4 WHERE mxid=$1",
            self.mxid,
            self.max_phone,
            self.max_session_file,
            self.management_room,
        )
