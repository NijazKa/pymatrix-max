from __future__ import annotations

from dataclasses import dataclass

from mautrix.types import EventID, RoomID, UserID
from mautrix.util.async_db import Database


@dataclass
class Reaction:
    """Mapping and state for a Matrix/MAX reaction.

    ``origin`` is ``matrix`` when a real Matrix user created the reaction and
    ``max`` when the bridge mirrored a remote MAX reaction into Matrix.
    MAX supports one active reaction per account and message, therefore old
    mappings are retained as inactive so later Matrix redactions don't remove
    a newer reaction accidentally.
    """

    db: Database

    mx_event: EventID
    mx_room: RoomID
    target_mx_event: EventID
    chat_id: str
    receiver: UserID | None
    max_message_id: str
    sender_mxid: UserID
    reaction: str
    origin: str
    active: bool = True

    @staticmethod
    def _receiver_key(receiver: UserID | None) -> str:
        return str(receiver) if receiver else ""

    @classmethod
    def _from_row(cls, row) -> "Reaction":
        receiver = row["receiver"] or None
        return cls(
            db=cls.db,
            mx_event=EventID(row["mx_event"]),
            mx_room=RoomID(row["mx_room"]),
            target_mx_event=EventID(row["target_mx_event"]),
            chat_id=row["chat_id"],
            receiver=UserID(receiver) if receiver else None,
            max_message_id=row["max_message_id"],
            sender_mxid=UserID(row["sender_mxid"]),
            reaction=row["reaction"],
            origin=row["origin"],
            active=bool(row["active"]),
        )

    @classmethod
    async def get_by_mx_event(
        cls,
        mx_room: RoomID,
        mx_event: EventID,
    ) -> "Reaction | None":
        row = await cls.db.fetchrow(
            "SELECT mx_event, mx_room, target_mx_event, chat_id, receiver, "
            "max_message_id, sender_mxid, reaction, origin, active "
            "FROM reaction_map WHERE mx_room=$1 AND mx_event=$2",
            mx_room,
            mx_event,
        )
        return cls._from_row(row) if row else None

    @classmethod
    async def get_active(
        cls,
        chat_id: str,
        receiver: UserID | None,
        max_message_id: str,
        sender_mxid: UserID,
        origin: str,
    ) -> "Reaction | None":
        row = await cls.db.fetchrow(
            "SELECT mx_event, mx_room, target_mx_event, chat_id, receiver, "
            "max_message_id, sender_mxid, reaction, origin, active "
            "FROM reaction_map "
            "WHERE chat_id=$1 AND receiver=$2 AND max_message_id=$3 "
            "AND sender_mxid=$4 AND origin=$5 AND active=TRUE "
            "LIMIT 1",
            chat_id,
            cls._receiver_key(receiver),
            max_message_id,
            sender_mxid,
            origin,
        )
        return cls._from_row(row) if row else None

    @classmethod
    async def deactivate_active(
        cls,
        chat_id: str,
        receiver: UserID | None,
        max_message_id: str,
        sender_mxid: UserID,
        origin: str,
    ) -> None:
        await cls.db.execute(
            "UPDATE reaction_map SET active=FALSE "
            "WHERE chat_id=$1 AND receiver=$2 AND max_message_id=$3 "
            "AND sender_mxid=$4 AND origin=$5 AND active=TRUE",
            chat_id,
            cls._receiver_key(receiver),
            max_message_id,
            sender_mxid,
            origin,
        )

    @classmethod
    async def delete_by_portal(
        cls,
        chat_id: str,
        receiver: UserID | None,
    ) -> None:
        await cls.db.execute(
            "DELETE FROM reaction_map WHERE chat_id=$1 AND receiver=$2",
            chat_id,
            cls._receiver_key(receiver),
        )

    async def insert(self) -> None:
        await self.db.execute(
            "INSERT INTO reaction_map "
            "(mx_event, mx_room, target_mx_event, chat_id, receiver, "
            "max_message_id, sender_mxid, reaction, origin, active) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) "
            "ON CONFLICT (mx_event) DO UPDATE SET "
            "mx_room=excluded.mx_room, target_mx_event=excluded.target_mx_event, "
            "chat_id=excluded.chat_id, receiver=excluded.receiver, "
            "max_message_id=excluded.max_message_id, "
            "sender_mxid=excluded.sender_mxid, reaction=excluded.reaction, "
            "origin=excluded.origin, active=excluded.active",
            self.mx_event,
            self.mx_room,
            self.target_mx_event,
            self.chat_id,
            self._receiver_key(self.receiver),
            self.max_message_id,
            self.sender_mxid,
            self.reaction,
            self.origin,
            self.active,
        )

    async def deactivate(self) -> None:
        self.active = False
        await self.db.execute(
            "UPDATE reaction_map SET active=FALSE WHERE mx_event=$1",
            self.mx_event,
        )
