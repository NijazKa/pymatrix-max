from __future__ import annotations

from dataclasses import dataclass

from mautrix.types import EventID, RoomID, UserID
from mautrix.util.async_db import Database


@dataclass
class Message:
    """Mapping between a MAX message and one or more Matrix events.

    A single MAX message can contain text and several attachments, while Matrix
    represents those as separate events. ``is_primary`` marks the Matrix event
    that replies from MAX should point to.
    """

    db: Database

    chat_id: str
    receiver: UserID | None
    max_message_id: str
    mx_room: RoomID
    mx_event: EventID
    is_primary: bool = False
    sender_max_id: str | None = None
    sender_name: str | None = None

    @staticmethod
    def _receiver_key(receiver: UserID | None) -> str:
        return str(receiver) if receiver else ""

    @classmethod
    def _from_row(cls, row) -> "Message":
        receiver = row["receiver"] or None
        return cls(
            db=cls.db,
            chat_id=row["chat_id"],
            receiver=UserID(receiver) if receiver else None,
            max_message_id=row["max_message_id"],
            mx_room=RoomID(row["mx_room"]),
            mx_event=EventID(row["mx_event"]),
            is_primary=bool(row["is_primary"]),
            sender_max_id=row["sender_max_id"] or None,
            sender_name=row["sender_name"] or None,
        )

    @classmethod
    async def get_by_mx_event(
        cls,
        mx_room: RoomID,
        mx_event: EventID,
    ) -> "Message | None":
        row = await cls.db.fetchrow(
            "SELECT chat_id, receiver, max_message_id, mx_room, mx_event, is_primary, "
            "sender_max_id, sender_name "
            "FROM message_map WHERE mx_room=$1 AND mx_event=$2",
            mx_room,
            mx_event,
        )
        return cls._from_row(row) if row else None

    @classmethod
    async def get_primary_by_max_id(
        cls,
        chat_id: str,
        receiver: UserID | None,
        max_message_id: str,
    ) -> "Message | None":
        row = await cls.db.fetchrow(
            "SELECT chat_id, receiver, max_message_id, mx_room, mx_event, is_primary, "
            "sender_max_id, sender_name "
            "FROM message_map "
            "WHERE chat_id=$1 AND receiver=$2 AND max_message_id=$3 "
            "ORDER BY is_primary DESC LIMIT 1",
            chat_id,
            cls._receiver_key(receiver),
            max_message_id,
        )
        return cls._from_row(row) if row else None

    @classmethod
    async def exists_by_max_id(
        cls,
        chat_id: str,
        receiver: UserID | None,
        max_message_id: str,
    ) -> bool:
        row = await cls.db.fetchrow(
            "SELECT 1 FROM message_map "
            "WHERE chat_id=$1 AND receiver=$2 AND max_message_id=$3 LIMIT 1",
            chat_id,
            cls._receiver_key(receiver),
            max_message_id,
        )
        return row is not None

    @classmethod
    async def delete_by_portal(
        cls,
        chat_id: str,
        receiver: UserID | None,
    ) -> None:
        await cls.db.execute(
            "DELETE FROM message_map WHERE chat_id=$1 AND receiver=$2",
            chat_id,
            cls._receiver_key(receiver),
        )

    async def insert(self) -> None:
        receiver_key = self._receiver_key(self.receiver)
        if self.is_primary:
            await self.db.execute(
                "UPDATE message_map SET is_primary=FALSE "
                "WHERE chat_id=$1 AND receiver=$2 AND max_message_id=$3",
                self.chat_id,
                receiver_key,
                self.max_message_id,
            )

        await self.db.execute(
            "INSERT INTO message_map "
            "(chat_id, receiver, max_message_id, mx_room, mx_event, is_primary, "
            "sender_max_id, sender_name) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
            "ON CONFLICT (mx_event) DO UPDATE SET "
            "chat_id=excluded.chat_id, receiver=excluded.receiver, "
            "max_message_id=excluded.max_message_id, mx_room=excluded.mx_room, "
            "is_primary=excluded.is_primary, "
            "sender_max_id=excluded.sender_max_id, sender_name=excluded.sender_name",
            self.chat_id,
            receiver_key,
            self.max_message_id,
            self.mx_room,
            self.mx_event,
            self.is_primary,
            self.sender_max_id,
            self.sender_name,
        )
