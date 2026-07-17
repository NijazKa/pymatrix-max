from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any

from mautrix.appservice import IntentAPI
from mautrix.bridge import BasePortal
from mautrix.errors.base import IntentError
from mautrix.types import (
    AudioInfo,
    EventID,
    EventType,
    FileInfo,
    ImageInfo,
    MediaMessageEventContent,
    ReactionEventContent,
    RelatesTo,
    RelationType,
    MessageEventContent,
    MessageType,
    RoomID,
    TextMessageEventContent,
    UserID,
    VideoInfo,
)

from . import db as db_module
from .puppet import Puppet

log = logging.getLogger("mau.portal")


class Portal(BasePortal):
    by_chat_id: dict[tuple[str, str | None], "Portal"] = {}
    by_mxid: dict[RoomID, "Portal"] = {}

    chat_id: str
    receiver: UserID | None
    mxid: RoomID | None
    name: str | None
    is_direct: bool
    remote_user_id: str | None
    _db_row: db_module.Portal

    def __init__(self, db_row: db_module.Portal) -> None:
        self._db_row = db_row
        self.chat_id = db_row.chat_id
        self.receiver = db_row.receiver
        self.mxid = db_row.mxid
        self.name = db_row.name
        self.is_direct = db_row.is_direct
        self.remote_user_id = db_row.remote_user_id
        self.encrypted = False
        self.relay_user_id = None
        self._relay_user = None
        super().__init__()

    @property
    def main_intent(self) -> IntentAPI:
        if self.is_direct and self.remote_user_id:
            puppet = Puppet.by_max_id.get(self.remote_user_id)
            if puppet is not None:
                return puppet.intent
        return self.az.intent

    @property
    def bridge_info_state_key(self) -> str:
        receiver = self.receiver or "shared"
        return f"net.maunium.max://max/{receiver}/{self.chat_id}"

    @property
    def bridge_info(self) -> dict[str, Any]:
        return {
            "bridgebot": self.az.bot_mxid,
            "creator": self.main_intent.mxid,
            "protocol": {"id": "max", "displayname": "MAX", "avatar_url": None},
            "channel": {
                "id": self.chat_id,
                "displayname": self.name or self.chat_id,
                "avatar_url": None,
            },
        }

    async def save(self) -> None:
        self._db_row.mxid = self.mxid
        self._db_row.name = self.name
        self._db_row.is_direct = self.is_direct
        self._db_row.remote_user_id = self.remote_user_id
        await self._db_row.save()

    async def delete(self) -> None:
        Portal.by_chat_id.pop(
            self._cache_key(self.chat_id, self.receiver, self.is_direct), None
        )
        if self.mxid:
            Portal.by_mxid.pop(self.mxid, None)
        await db_module.Message.delete_by_portal(self.chat_id, self.receiver)
        await db_module.Reaction.delete_by_portal(self.chat_id, self.receiver)
        if not self.is_direct:
            await db_module.PortalUser.delete_by_chat(self.chat_id)
        await self._db_row.delete()

    async def get_dm_puppet(self) -> Puppet | None:
        if not self.remote_user_id:
            return None
        return await Puppet.get_by_max_id(self.remote_user_id, create=False)

    async def remember_matrix_user(self, mxid: UserID) -> None:
        """Associate a Matrix/MAX account with this shared group portal."""
        if self.is_direct:
            return
        await db_module.PortalUser.add(self.chat_id, mxid)

    async def forget_matrix_user(self, mxid: UserID) -> bool:
        """Remove a Matrix/MAX account from this shared group portal."""
        if self.is_direct:
            return False
        return await db_module.PortalUser.remove(self.chat_id, mxid)

    async def ensure_matrix_user(
        self,
        mxid: UserID,
        *,
        reason: str = "Доступ к общему MAX-чату",
    ) -> bool:
        """Persist access and invite the Matrix user to an existing room.

        Invitation failures are deliberately non-fatal: an incoming MAX
        message must still be bridged even when Matrix temporarily rejects the
        invite. The association remains in ``portal_user`` and later events or
        startup reconciliation will retry it.
        """
        if self.is_direct:
            return False

        await self.remember_matrix_user(mxid)
        if self.mxid is None:
            return False

        try:
            await self.main_intent.invite_user(
                self.mxid,
                mxid,
                reason=reason,
                check_cache=True,
            )
        except Exception:
            log.warning(
                "Не удалось пригласить Matrix-пользователя в общий MAX portal: "
                "chat=%s room=%s mxid=%s",
                self.chat_id,
                self.mxid,
                mxid,
                exc_info=True,
            )
            return False

        log.debug(
            "Проверено приглашение Matrix-пользователя в MAX portal: "
            "chat=%s room=%s mxid=%s",
            self.chat_id,
            self.mxid,
            mxid,
        )
        return True

    @classmethod
    def _cache_key(
        cls,
        chat_id: str,
        receiver: UserID | None,
        is_direct: bool,
    ) -> tuple[str, str | None]:
        return (chat_id, str(receiver) if is_direct and receiver else None)

    @classmethod
    async def get_by_chat_id(
        cls,
        chat_id: str,
        receiver: UserID | None,
        create: bool = True,
        is_direct: bool = True,
    ) -> "Portal | None":
        effective_receiver = receiver if is_direct else None
        cache_key = cls._cache_key(chat_id, receiver, is_direct)
        if cache_key in cls.by_chat_id:
            return cls.by_chat_id[cache_key]

        row = await db_module.Portal.get_by_chat_id(chat_id, effective_receiver)
        if not row:
            if not create:
                return None
            row = db_module.Portal(
                db=db_module.Portal.db,
                chat_id=chat_id,
                receiver=effective_receiver,
                mxid=None,
                name=None,
                is_direct=is_direct,
                remote_user_id=None,
            )
            await row.insert()

        portal = cls(row)
        cls.by_chat_id[cache_key] = portal
        if portal.mxid:
            cls.by_mxid[portal.mxid] = portal
        return portal

    @classmethod
    async def get_by_mxid(cls, mxid: RoomID) -> "Portal | None":
        if mxid in cls.by_mxid:
            return cls.by_mxid[mxid]
        row = await db_module.Portal.get_by_mxid(mxid)
        if not row:
            return None
        portal = cls(row)
        cls.by_mxid[mxid] = portal
        cls.by_chat_id[cls._cache_key(row.chat_id, row.receiver, row.is_direct)] = portal
        return portal

    def _group_messages_via_bot(self) -> bool:
        """Return whether shared chats should use the bridge bot as sender.

        Sending group messages from individual ghost users requires registering
        every remote participant on Synapse. The production default is relay
        mode: one bridge bot sends the event and prefixes the original MAX
        sender name in the body. Direct chats always keep their dedicated ghost.
        """
        try:
            value = self.bridge.config["bridge.group_messages_via_bot"]
        except Exception:
            return True
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off"}
        return value is not False

    @staticmethod
    def _display_name_from_info(info) -> str | None:
        if info is None:
            return None
        if isinstance(info, dict):
            direct = str(info.get("name") or "").strip()
            if direct:
                return direct
            contact = info.get("contact")
        else:
            name = Puppet.display_name_from_info(info)
            if name:
                return name
            contact = getattr(info, "contact", None)

        if isinstance(contact, dict):
            return str(contact.get("name") or "").strip() or None
        return Puppet.display_name_from_info(contact)

    async def _resolve_group_sender_name(
        self,
        source: "User",
        sender_max_id: str | None,
        chat_info,
    ) -> str:
        """Resolve a group sender name without creating/registering a puppet."""
        if not sender_max_id:
            return self.name or f"MAX {self.chat_id}"

        participants = getattr(chat_info, "participants", None) or {}
        candidates = [participants.get(sender_max_id)]
        try:
            candidates.append(participants.get(int(sender_max_id)))
        except (TypeError, ValueError):
            pass

        for candidate in candidates:
            name = self._display_name_from_info(candidate)
            if name:
                return name

        # Existing local metadata may belong to a real DM. Reading the bridge
        # row directly is safe: unlike Puppet.get_by_max_id(), it does not
        # register a Matrix user.
        try:
            row = await db_module.Puppet.get_by_max_id(sender_max_id)
        except Exception:
            row = None
        if row is not None and row.name:
            return row.name

        try:
            info = await source.max_client.get_user_info(int(sender_max_id))
        except Exception:
            log.debug(
                "Не удалось получить имя участника MAX-группы %s",
                sender_max_id,
                exc_info=True,
            )
        else:
            name = self._display_name_from_info(info)
            if name:
                return name

        return f"MAX {sender_max_id}"

    def _media_max_size(self) -> int:
        try:
            value = self.bridge.config["bridge.media.max_size"]
            return int(value)
        except Exception:
            return 100 * 1024 * 1024

    @staticmethod
    def _chat_is_direct(chat_info, fallback: bool) -> bool:
        # PyMax Chat exposes a reliable boolean property in current versions.
        is_dialog = getattr(chat_info, "is_dialog", None)
        if isinstance(is_dialog, bool):
            return is_dialog

        chat_type = getattr(chat_info, "type", None)
        value = getattr(chat_type, "value", chat_type)
        if value is None:
            return fallback

        normalized = str(value).upper()
        return normalized in {
            "DIALOG",
            "DIRECT",
            "DM",
            "CHATTYPE.DIALOG",
        }

    @staticmethod
    def _placeholder_name(name: str | None) -> bool:
        if not name:
            return True
        lowered = name.lower()
        return lowered.startswith("max_") or lowered.isdigit()

    @staticmethod
    def _dm_contact_topic(puppet: Puppet) -> str | None:
        if not puppet.phone:
            return None
        return f"Телефон MAX: {puppet.phone}"

    async def sync_dm_contact_topic(
        self,
        puppet: Puppet,
        *,
        clear_if_missing: bool = False,
    ) -> bool:
        """Обновить или очистить тему личной комнаты по данным контакта MAX."""
        if not self.is_direct or self.mxid is None:
            return False
        topic = self._dm_contact_topic(puppet)
        if topic is None:
            if not clear_if_missing:
                return False
            topic = ""

        try:
            await puppet.intent.set_room_topic(self.mxid, topic)
        except IntentError:
            log.debug(
                "Ghost %s не может изменить тему комнаты %s; телефон сохранён в БД",
                puppet.intent.mxid,
                self.mxid,
            )
            return False
        return True

    async def _resolve_direct_puppet(
        self,
        source: "User",
        puppet: Puppet | None,
        chat_info,
    ) -> tuple[Puppet | None, set[str]]:
        """Найти ghost собеседника и вернуть изменения его профиля."""
        if self.remote_user_id:
            return await Puppet.get_by_max_id(self.remote_user_id), set()

        remote_user_id: str | None = None
        changes: set[str] = set()

        own_user_id: str | None = None
        try:
            me = await source.max_client.get_me()
            contact = getattr(me, "contact", None)
            raw_own_id = getattr(contact, "id", None)
            if raw_own_id is None:
                raw_own_id = getattr(me, "id", None)
            if raw_own_id is not None:
                own_user_id = str(raw_own_id)
        except Exception:
            log.debug(
                "Не удалось определить собственный MAX user ID для %s",
                source.mxid,
                exc_info=True,
            )

        if puppet is not None and puppet.max_user_id != own_user_id:
            remote_user_id = puppet.max_user_id

        if not remote_user_id:
            participants = getattr(chat_info, "participants", None) or {}
            participant_ids = [str(value) for value in participants.keys()]
            for participant_id in participant_ids:
                if participant_id != own_user_id:
                    remote_user_id = participant_id
                    break

        if not remote_user_id:
            return None, changes

        puppet = await Puppet.get_by_max_id(remote_user_id)
        if puppet is None:
            return None, changes

        self.remote_user_id = puppet.max_user_id

        try:
            user_info = await source.max_client.get_user_info(int(remote_user_id))
            changes |= await puppet.update_info(user_info)
        except Exception:
            log.debug(
                "Не удалось обновить профиль MAX user %s",
                remote_user_id,
                exc_info=True,
            )

        return puppet, changes

    @staticmethod
    def _reply_mapping(value: Any) -> dict[str, Any] | None:
        """Convert PyMax/Pydantic reply metadata to a plain mapping."""
        if isinstance(value, dict):
            return value

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            try:
                dumped = model_dump(by_alias=True, exclude_none=True)
            except TypeError:
                dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped

        value_dict = getattr(value, "__dict__", None)
        return value_dict if isinstance(value_dict, dict) else None

    @staticmethod
    def _reply_scalar_id(value: Any) -> str | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (str, int)):
            value = str(value).strip()
            return value or None
        return None

    @classmethod
    def _reply_id_from_value(
        cls,
        value: Any,
        *,
        allow_generic_id: bool = False,
        depth: int = 0,
    ) -> str | None:
        """Extract a MAX message ID from one reply/quote container.

        MAX uses more than one inbound representation. Besides the outbound
        ``{type: REPLY, messageId: ...}`` shape, push events may contain a
        complete quoted message under ``link.message``. Keep the traversal
        limited to explicit reply containers to avoid confusing the current
        message ID with the replied-to ID.
        """
        if depth > 4:
            return None

        if allow_generic_id:
            scalar = cls._reply_scalar_id(value)
            if scalar:
                return scalar

        data = cls._reply_mapping(value)
        if not data:
            return None

        direct_id_keys = (
            "messageId",
            "message_id",
            "msgId",
            "msg_id",
            "replyMessageId",
            "reply_message_id",
            "replyToMessageId",
            "reply_to_message_id",
        )
        for key in direct_id_keys:
            message_id = cls._reply_scalar_id(data.get(key))
            if message_id:
                return message_id

        if allow_generic_id:
            for key in ("id", "mid"):
                message_id = cls._reply_scalar_id(data.get(key))
                if message_id:
                    return message_id

        # Incoming MAX replies commonly contain the complete original message
        # rather than a top-level messageId.
        nested_message_keys = (
            "message",
            "linkedMessage",
            "linked_message",
            "replyMessage",
            "reply_message",
            "quotedMessage",
            "quoted_message",
            "quoteMessage",
            "quote_message",
        )
        for key in nested_message_keys:
            if key not in data:
                continue
            message_id = cls._reply_id_from_value(
                data[key],
                allow_generic_id=True,
                depth=depth + 1,
            )
            if message_id:
                return message_id

        # Some clients add another reply/link wrapper around the quoted
        # message object.
        for key in ("reply", "replyTo", "reply_to", "quote", "link"):
            if key not in data:
                continue
            message_id = cls._reply_id_from_value(
                data[key],
                allow_generic_id=True,
                depth=depth + 1,
            )
            if message_id:
                return message_id

        return None

    @classmethod
    def _max_reply_metadata(cls, message) -> dict[str, Any]:
        data = cls._reply_mapping(message) or {}
        keys = (
            "link",
            "reply",
            "replyTo",
            "reply_to",
            "replyMessage",
            "reply_message",
            "replyMessageId",
            "reply_message_id",
            "quotedMessage",
            "quoted_message",
            "quote",
        )
        return {key: data[key] for key in keys if key in data and data[key] is not None}

    @classmethod
    def _max_reply_id(cls, message) -> str | None:
        """Extract the replied-to MAX message ID from all known wire shapes."""
        data = cls._reply_mapping(message) or {}

        # Explicit top-level reply fields don't need a link type discriminator.
        for key in (
            "replyTo",
            "reply_to",
            "reply",
            "replyMessage",
            "reply_message",
            "replyMessageId",
            "reply_message_id",
            "quotedMessage",
            "quoted_message",
            "quote",
        ):
            if key not in data:
                continue
            message_id = cls._reply_id_from_value(
                data[key],
                allow_generic_id=True,
            )
            if message_id:
                return message_id

        link = data.get("link", getattr(message, "link", None))
        link_data = cls._reply_mapping(link)
        if not link_data:
            return None

        link_type = link_data.get(
            "type",
            link_data.get("linkType", link_data.get("link_type")),
        )
        link_type = getattr(link_type, "value", link_type)
        normalized_type = str(link_type or "").upper()

        # Do not turn FORWARD links into Matrix replies. A missing type is
        # accepted only when the container itself clearly contains reply data.
        if normalized_type and "REPLY" not in normalized_type and "QUOTE" not in normalized_type:
            return None
        if not normalized_type and not any(
            key in link_data
            for key in (
                "messageId",
                "message_id",
                "message",
                "reply",
                "replyTo",
                "reply_to",
                "quotedMessage",
                "quoted_message",
            )
        ):
            return None

        return cls._reply_id_from_value(link_data)

    async def _matrix_reply_target(self, message) -> EventID | None:
        reply_to_max = self._max_reply_id(message)
        if not reply_to_max:
            metadata = self._max_reply_metadata(message)
            if metadata:
                log.debug(
                    "MAX reply metadata не распознаны в чате %s: %r",
                    self.chat_id,
                    metadata,
                )
            return None

        mapped = await db_module.Message.get_primary_by_max_id(
            self.chat_id,
            self.receiver,
            reply_to_max,
        )
        if mapped is None:
            log.debug(
                "Не найден Matrix event для MAX reply %s в чате %s",
                reply_to_max,
                self.chat_id,
            )
            return None

        log.debug(
            "MAX reply сопоставлен: chat=%s max_message=%s mx_event=%s",
            self.chat_id,
            reply_to_max,
            mapped.mx_event,
        )
        return mapped.mx_event

    async def _store_message_mapping(
        self,
        max_message_id: str,
        mx_event: EventID,
        *,
        primary: bool,
        sender_max_id: str | None = None,
        sender_name: str | None = None,
    ) -> None:
        if not self.mxid:
            raise RuntimeError("Нельзя сохранить mapping до создания Matrix-комнаты")
        await db_module.Message(
            db=db_module.Message.db,
            chat_id=self.chat_id,
            receiver=self.receiver,
            max_message_id=max_message_id,
            mx_room=self.mxid,
            mx_event=mx_event,
            is_primary=primary,
            sender_max_id=sender_max_id,
            sender_name=sender_name,
        ).insert()

    async def _send_max_content_to_matrix(
        self,
        intent: IntentAPI,
        content: MessageEventContent,
        *,
        max_message_id: str,
        reply_to: EventID | None,
        primary: bool,
        sender_max_id: str | None = None,
        sender_name: str | None = None,
    ) -> EventID:
        if reply_to:
            content.set_reply(reply_to)
        event_id = await self._send_message(intent, content, EventType.ROOM_MESSAGE)
        await self._store_message_mapping(
            max_message_id,
            event_id,
            primary=primary,
            sender_max_id=sender_max_id,
            sender_name=sender_name,
        )
        return event_id

    async def handle_max_message(self, source: "User", message, chat_info=None) -> None:
        if message.chat_id is None:
            log.debug("Игнорирую MAX-сообщение без chat_id")
            return

        max_message_id = str(getattr(message, "id", "") or "")
        if not max_message_id:
            log.warning("Игнорирую MAX-сообщение без message.id в чате %s", self.chat_id)
            return

        if await db_module.Message.exists_by_max_id(
            self.chat_id,
            self.receiver,
            max_message_id,
        ):
            log.debug(
                "MAX-сообщение %s в чате %s уже сопоставлено, пропускаю эхо/дубликат",
                max_message_id,
                self.chat_id,
            )
            return

        if chat_info is None:
            chat_info = await source.max_client.get_chat_info(int(self.chat_id))

        detected_direct = self._chat_is_direct(chat_info, self.is_direct)
        # Never downgrade an existing two-user portal to a group portal. Older
        # rooms may already have been created by a ghost and intentionally do
        # not contain the bridge bot.
        if self.mxid:
            self.is_direct = self.is_direct or detected_direct
        else:
            self.is_direct = detected_direct

        raw_sender_id = getattr(message, "sender", None)
        sender_max_id = str(raw_sender_id) if raw_sender_id is not None else None
        sender_name: str | None = None
        puppet: Puppet | None = None
        profile_changes: set[str] = set()
        group_relay = not self.is_direct and self._group_messages_via_bot()

        if self.is_direct:
            if sender_max_id is not None:
                puppet = await Puppet.get_by_max_id(sender_max_id)
                if puppet is not None:
                    try:
                        user_info = await source.max_client.get_user_info(int(sender_max_id))
                        profile_changes |= await puppet.update_info(user_info)
                    except Exception:
                        log.exception("Не удалось обновить профиль MAX user %s", sender_max_id)

            puppet, resolved_changes = await self._resolve_direct_puppet(
                source, puppet, chat_info
            )
            profile_changes |= resolved_changes
            if puppet is None:
                # Не используем bridge bot как отправителя в DM: иначе он станет
                # третьим участником комнаты или не сможет в неё вступить.
                log.warning(
                    "Не удалось определить ghost собеседника для личного чата %s; "
                    "сообщение временно пропущено",
                    self.chat_id,
                )
                return

            if not self.remote_user_id:
                self.remote_user_id = puppet.max_user_id
                await self.save()
            if self._placeholder_name(self.name):
                self.name = puppet.name or f"MAX {puppet.max_user_id}"
            sender_name = puppet.name or f"MAX {puppet.max_user_id}"
        else:
            self.name = getattr(chat_info, "title", None) or self.name or f"MAX {self.chat_id}"
            if group_relay:
                # Critical production behaviour: do not instantiate Puppet here.
                # Puppet.get_by_max_id() registers a Synapse user; group relay
                # deliberately keeps all remote participants out of Synapse.
                sender_name = await self._resolve_group_sender_name(
                    source, sender_max_id, chat_info
                )
            else:
                if sender_max_id is not None:
                    puppet = await Puppet.get_by_max_id(sender_max_id)
                    if puppet is not None:
                        try:
                            user_info = await source.max_client.get_user_info(int(sender_max_id))
                            profile_changes |= await puppet.update_info(user_info)
                        except Exception:
                            log.exception("Не удалось обновить профиль MAX user %s", sender_max_id)
                if puppet is None:
                    log.warning(
                        "MAX-событие без определяемого отправителя для чата %s пропущено",
                        self.chat_id,
                    )
                    return
                sender_name = puppet.name or f"MAX {puppet.max_user_id}"

        if group_relay:
            send_intent = self.az.intent
        else:
            if puppet is None and self.remote_user_id:
                puppet = await Puppet.get_by_max_id(self.remote_user_id)
            if puppet is None:
                log.warning(
                    "MAX-событие без определяемого отправителя для чата %s пропущено",
                    self.chat_id,
                )
                return
            send_intent = puppet.intent

        if not self.mxid:
            await self.create_matrix_room(
                source,
                puppet if self.is_direct or not group_relay else None,
                chat_info,
            )

        # The bot creates relay group rooms and is already joined. Ghost mode
        # still needs to join the remote sender before sending the event.
        if not self.is_direct and not group_relay:
            await send_intent.ensure_joined(self.mxid)
        elif self.is_direct and "phone" in profile_changes:
            await self.sync_dm_contact_topic(puppet, clear_if_missing=True)

        if (
            self.is_direct
            and puppet is not None
            and puppet.name
            and self._placeholder_name(self._db_row.name)
        ):
            self.name = puppet.name
            try:
                await send_intent.set_room_name(self.mxid, self.name)
            except IntentError:
                log.debug(
                    "Ghost %s не может изменить имя комнаты %s; "
                    "сохраняю имя portal и продолжаю доставку сообщения",
                    send_intent.mxid,
                    self.mxid,
                )
            await self.save()

        reply_to_event = await self._matrix_reply_target(message)
        primary_sent = False
        relay_header_sent = False

        message_text = str(getattr(message, "text", "") or "").strip()
        attachments = getattr(message, "attaches", None) or []
        log_text = message_text
        if len(log_text) > 2000:
            log_text = f"{log_text[:2000]}… <обрезано, всего {len(message_text)} символов>"
        log.info(
            "MAX→Matrix: account=%s phone=%s chat=%s message=%s sender=%s "
            "sender_name=%r relay=%s reply_max=%s reply_event=%s text=%r attachments=%s",
            source.mxid,
            getattr(source, "max_phone", None) or "неизвестен",
            self.chat_id,
            max_message_id,
            sender_max_id,
            sender_name,
            group_relay,
            self._max_reply_id(message),
            reply_to_event,
            log_text,
            [type(attachment).__name__ for attachment in attachments],
        )
        if message_text:
            body = f"{sender_name}: {message_text}" if group_relay else message_text
            content = TextMessageEventContent(
                msgtype=MessageType.TEXT,
                body=body,
            )
            await self._send_max_content_to_matrix(
                send_intent,
                content,
                max_message_id=max_message_id,
                reply_to=reply_to_event,
                primary=True,
                sender_max_id=sender_max_id,
                sender_name=sender_name,
            )
            primary_sent = True

        for attachment in attachments:
            try:
                media = await source.max_client.download_attachment(
                    message,
                    attachment,
                    max_size=self._media_max_size(),
                )
                if media is None:
                    log.debug("Неподдерживаемое вложение MAX: %s", type(attachment).__name__)
                    continue

                # Media event bodies are not shown as captions by every Matrix
                # client. For attachment-only group messages, send one compact
                # sender header without making it the reply target.
                if group_relay and not message_text and not relay_header_sent:
                    header = TextMessageEventContent(
                        msgtype=MessageType.NOTICE,
                        body=f"{sender_name}: вложение",
                    )
                    await self._send_max_content_to_matrix(
                        send_intent,
                        header,
                        max_message_id=max_message_id,
                        reply_to=None,
                        primary=False,
                        sender_max_id=sender_max_id,
                        sender_name=sender_name,
                    )
                    relay_header_sent = True

                mxc = await send_intent.upload_media(
                    media.data,
                    mime_type=media.mime_type,
                    filename=media.filename,
                    size=media.size,
                )

                if media.kind == "image":
                    info = ImageInfo(
                        mimetype=media.mime_type,
                        size=media.size,
                        width=media.width,
                        height=media.height,
                    )
                    msgtype = MessageType.IMAGE
                elif media.kind == "video":
                    info = VideoInfo(
                        mimetype=media.mime_type,
                        size=media.size,
                        width=media.width,
                        height=media.height,
                        duration=media.duration_ms,
                    )
                    msgtype = MessageType.VIDEO
                elif media.kind == "audio":
                    info = AudioInfo(
                        mimetype=media.mime_type,
                        size=media.size,
                        duration=media.duration_ms,
                    )
                    msgtype = MessageType.AUDIO
                else:
                    info = FileInfo(mimetype=media.mime_type, size=media.size)
                    msgtype = MessageType.FILE

                media_body = (
                    f"{sender_name}: {media.filename}" if group_relay else media.filename
                )
                content = MediaMessageEventContent(
                    msgtype=msgtype,
                    body=media_body,
                    filename=media.filename,
                    url=mxc,
                    info=info,
                )
                await self._send_max_content_to_matrix(
                    send_intent,
                    content,
                    max_message_id=max_message_id,
                    reply_to=reply_to_event if not primary_sent else None,
                    primary=not primary_sent,
                    sender_max_id=sender_max_id,
                    sender_name=sender_name,
                )
                primary_sent = True
            except Exception:
                log.exception(
                    "Не удалось передать вложение MAX %s в Matrix",
                    type(attachment).__name__,
                )

    async def create_matrix_room(
        self,
        source: "User",
        dm_puppet: Puppet | None = None,
        chat_info=None,
    ) -> RoomID:
        # Для !max add ID личного чата вычисляется локально из двух MAX user
        # ID. Такого диалога может ещё не быть в списке чатов, поэтому не
        # требуем get_chat() перед созданием Matrix-комнаты, если ghost уже
        # известен и portal явно помечен как direct.
        if chat_info is None and not (self.is_direct and dm_puppet is not None):
            chat_info = await source.max_client.get_chat_info(int(self.chat_id))

        detected_direct = self._chat_is_direct(chat_info, self.is_direct)
        self.is_direct = self.is_direct or detected_direct
        if self.is_direct and dm_puppet is not None:
            self.remote_user_id = dm_puppet.max_user_id
            self.name = dm_puppet.name or f"MAX {dm_puppet.max_user_id}"
            room_intent = dm_puppet.intent
        else:
            self.name = getattr(chat_info, "title", None) or self.name or f"MAX {self.chat_id}"
            room_intent = self.az.intent

        if self.is_direct:
            invitees = [source.mxid]
        else:
            await self.remember_matrix_user(source.mxid)
            invitees = await db_module.PortalUser.get_users(self.chat_id)
            if source.mxid not in invitees:
                invitees.append(source.mxid)

        room_id = await room_intent.create_room(
            name=self.name,
            invitees=invitees,
            is_direct=self.is_direct,
        )
        self.mxid = room_id
        if self.is_direct and dm_puppet is not None:
            await self.sync_dm_contact_topic(dm_puppet)
        await self.save()
        Portal.by_mxid[room_id] = self
        return room_id

    @staticmethod
    def _info_value(info, key: str, default=None):
        if info is None:
            return default
        if isinstance(info, dict):
            return info.get(key, default)
        return getattr(info, key, default)

    async def _matrix_download_intent(self) -> IntentAPI:
        if self.is_direct:
            puppet = await self.get_dm_puppet()
            if puppet is not None:
                return puppet.intent
        return self.main_intent

    async def _max_reply_target(self, message: MessageEventContent) -> int | None:
        try:
            reply_event_id = message.get_reply_to()
        except AttributeError:
            reply_event_id = None

        if not reply_event_id or not self.mxid:
            return None

        mapped = await db_module.Message.get_by_mx_event(self.mxid, reply_event_id)
        if mapped is None:
            log.debug(
                "Не найден MAX message ID для Matrix reply %s в комнате %s",
                reply_event_id,
                self.mxid,
            )
            return None

        try:
            return int(mapped.max_message_id)
        except (TypeError, ValueError):
            log.warning("Некорректный MAX message ID в БД: %r", mapped.max_message_id)
            return None

    async def _store_outgoing_mapping(self, event_id: EventID, sent_message) -> None:
        max_message_id = getattr(sent_message, "id", None)
        if max_message_id is None:
            log.warning(
                "MAX не вернул ID отправленного сообщения для Matrix event %s",
                event_id,
            )
            return

        await self._store_message_mapping(
            str(max_message_id),
            event_id,
            primary=True,
        )

    async def handle_matrix_reaction(
        self,
        sender: "User",
        target_event_id: EventID,
        reaction: str,
        reaction_event_id: EventID,
    ) -> None:
        """Передать Matrix m.reaction в MAX."""
        if self.is_direct and self.receiver and sender.mxid != self.receiver:
            log.warning(
                "%s попытался поставить реакцию в чужом MAX-чате %s",
                sender.mxid,
                self.chat_id,
            )
            return

        if not self.mxid or not sender.max_client or not sender.max_client.is_ready:
            return

        mapped = await db_module.Message.get_by_mx_event(
            self.mxid,
            target_event_id,
        )
        if mapped is None:
            log.debug(
                "Не найден MAX message ID для Matrix-реакции %s на %s",
                reaction_event_id,
                target_event_id,
            )
            return

        reaction = reaction.strip()
        if not reaction:
            return

        await sender.max_client.add_reaction(
            chat_id=int(self.chat_id),
            message_id=mapped.max_message_id,
            reaction=reaction,
        )

        # MAX хранит одну реакцию текущего аккаунта на сообщение. Новая
        # реакция заменяет предыдущую, поэтому старые Matrix mappings делаем
        # неактивными, но не удаляем: их последующая redaction не должна снять
        # уже новую реакцию в MAX.
        await db_module.Reaction.deactivate_active(
            self.chat_id,
            self.receiver,
            mapped.max_message_id,
            sender.mxid,
            "matrix",
        )
        await db_module.Reaction(
            db=db_module.Reaction.db,
            mx_event=reaction_event_id,
            mx_room=self.mxid,
            target_mx_event=target_event_id,
            chat_id=self.chat_id,
            receiver=self.receiver,
            max_message_id=mapped.max_message_id,
            sender_mxid=sender.mxid,
            reaction=reaction,
            origin="matrix",
            active=True,
        ).insert()

        log.info(
            "Matrix-реакция %s передана в MAX message %s",
            reaction,
            mapped.max_message_id,
        )

    async def handle_matrix_reaction_redaction(
        self,
        sender: "User",
        redacted_event_id: EventID,
        redaction_event_id: EventID,
    ) -> bool:
        """Удалить реакцию MAX при redaction соответствующей Matrix-реакции."""
        if not self.mxid:
            return False

        mapped = await db_module.Reaction.get_by_mx_event(
            self.mxid,
            redacted_event_id,
        )
        if mapped is None:
            return False

        # Redaction bridge-generated MAX->Matrix reaction must not change MAX.
        if mapped.origin != "matrix":
            return True

        if mapped.sender_mxid != sender.mxid:
            log.warning(
                "%s попытался удалить чужую реакцию %s",
                sender.mxid,
                redacted_event_id,
            )
            return True

        if mapped.active and sender.max_client and sender.max_client.is_ready:
            await sender.max_client.remove_reaction(
                chat_id=int(self.chat_id),
                message_id=mapped.max_message_id,
            )
            log.info(
                "Matrix-реакция %s удалена из MAX message %s",
                mapped.reaction,
                mapped.max_message_id,
            )

        await mapped.deactivate()
        return True

    async def handle_max_reaction_update(
        self,
        source: "User",
        event,
        chat_info=None,
    ) -> None:
        """Синхронизировать реакции MAX в Matrix.

        MAX присылает только агрегированные counters без ID реагировавших. В
        личном чате второй участник известен, поэтому его реакцию можно
        восстановить точно. В группах реакции Matrix->MAX поддерживаются, а
        входящие агрегаты пока только логируются.
        """
        if not self.mxid:
            return

        max_message_id = str(getattr(event, "message_id", "") or "")
        if not max_message_id:
            return

        target = await db_module.Message.get_primary_by_max_id(
            self.chat_id,
            self.receiver,
            max_message_id,
        )
        if target is None:
            log.debug(
                "Не найден Matrix event для обновления реакций MAX message %s",
                max_message_id,
            )
            return

        reaction_data = await source.max_client.get_reactions(
            chat_id=int(self.chat_id),
            message_ids=[max_message_id],
        )
        info = reaction_data.get(max_message_id) if reaction_data else None
        own_reaction = getattr(info, "your_reaction", None) if info else None

        # Если реакцию текущего аккаунта изменили или удалили непосредственно
        # в приложении MAX, старый Matrix-origin mapping больше не должен
        # считаться активным. Создать событие от реального Matrix-пользователя
        # без double puppeting мост не может.
        own_mapping = await db_module.Reaction.get_active(
            self.chat_id,
            self.receiver,
            max_message_id,
            source.mxid,
            "matrix",
        )
        if own_mapping and own_mapping.reaction != own_reaction:
            await own_mapping.deactivate()

        if not self.is_direct:
            counters = [
                (str(getattr(counter, "reaction", "")), int(getattr(counter, "count", 0)))
                for counter in (getattr(event, "counters", None) or [])
            ]
            log.debug(
                "Получены агрегированные реакции MAX для группового message %s: %s; "
                "ID авторов протокол не передал",
                max_message_id,
                counters,
            )
            return

        puppet = await self.get_dm_puppet()
        if puppet is None:
            return

        remote_reactions: list[str] = []
        counters = getattr(info, "counters", None) if info else None
        if counters is None:
            counters = getattr(event, "counters", None) or []

        for counter in counters:
            emoji = str(getattr(counter, "reaction", "") or "")
            count = int(getattr(counter, "count", 0) or 0)
            if own_reaction == emoji:
                count -= 1
            if emoji and count > 0:
                remote_reactions.append(emoji)

        desired = remote_reactions[0] if remote_reactions else None
        if len(remote_reactions) > 1:
            log.warning(
                "Для DM message %s получено несколько реакций второго участника: %s",
                max_message_id,
                remote_reactions,
            )

        current = await db_module.Reaction.get_active(
            self.chat_id,
            self.receiver,
            max_message_id,
            puppet.mxid,
            "max",
        )
        if current and current.reaction == desired:
            return

        if current:
            try:
                await puppet.intent.redact(
                    self.mxid,
                    current.mx_event,
                    reason="MAX reaction changed",
                )
            except Exception:
                log.exception(
                    "Не удалось удалить старую Matrix-реакцию %s",
                    current.mx_event,
                )
            await current.deactivate()

        if not desired:
            return

        content = ReactionEventContent()
        content.relates_to = RelatesTo(
            rel_type=RelationType.ANNOTATION,
            event_id=target.mx_event,
            key=desired,
        )
        mx_event = await self._send_message(
            puppet.intent,
            content,
            EventType.REACTION,
        )
        await db_module.Reaction(
            db=db_module.Reaction.db,
            mx_event=mx_event,
            mx_room=self.mxid,
            target_mx_event=target.mx_event,
            chat_id=self.chat_id,
            receiver=self.receiver,
            max_message_id=max_message_id,
            sender_mxid=puppet.mxid,
            reaction=desired,
            origin="max",
            active=True,
        ).insert()

        log.info(
            "MAX-реакция %s на message %s передана в Matrix",
            desired,
            max_message_id,
        )

    async def handle_matrix_message(
        self,
        sender: "User",
        message: MessageEventContent,
        event_id: EventID,
    ) -> None:
        if self.is_direct and self.receiver and sender.mxid != self.receiver:
            log.warning(
                "%s попытался написать в чужой личный MAX-чат %s, игнорирую",
                sender.mxid,
                self.chat_id,
            )
            return

        if not sender.max_client or not sender.max_client.is_ready:
            log.debug("%s не залогинен в MAX, сообщение не отправлено", sender.mxid)
            return

        reply_to_max = await self._max_reply_target(message)
        try:
            message.trim_reply_fallback()
        except AttributeError:
            pass

        msgtype = getattr(message, "msgtype", MessageType.TEXT)
        if getattr(msgtype, "is_text", False):
            sent_message = await sender.max_client.send_message(
                chat_id=int(self.chat_id),
                text=message.body,
                reply_to=reply_to_max,
            )
            await self._store_outgoing_mapping(event_id, sent_message)
            return

        if not getattr(msgtype, "is_media", False):
            log.debug("Неподдерживаемый Matrix msgtype: %s", msgtype)
            return

        media_message = message
        if not isinstance(media_message, MediaMessageEventContent):
            log.warning("Matrix media content имеет неожиданный тип %s", type(message).__name__)
            return
        if media_message.file is not None:
            log.warning("Зашифрованные Matrix-медиа пока не поддерживаются")
            return
        if not media_message.url:
            log.warning("Matrix media event без url")
            return

        download_intent = await self._matrix_download_intent()
        data = await download_intent.download_media(media_message.url)
        max_size = self._media_max_size()
        if len(data) > max_size:
            raise ValueError(f"Matrix-медиа больше лимита {max_size} байт")

        info = media_message.info
        mime_type = self._info_value(info, "mimetype", None) or "application/octet-stream"
        default_ext = mimetypes.guess_extension(mime_type) or ".bin"
        filename = media_message.filename or media_message.body or f"matrix_media{default_ext}"
        filename = Path(filename).name
        if not Path(filename).suffix:
            filename += default_ext

        if msgtype == MessageType.IMAGE:
            kind = "image"
        elif msgtype == MessageType.VIDEO:
            kind = "video"
        elif msgtype == MessageType.AUDIO:
            kind = "audio"
        else:
            kind = "file"

        caption = ""
        if media_message.filename and media_message.body != media_message.filename:
            caption = media_message.body

        sent_message = await sender.max_client.send_media(
            chat_id=int(self.chat_id),
            data=data,
            filename=filename,
            kind=kind,
            caption=caption,
            reply_to=reply_to_max,
        )
        await self._store_outgoing_mapping(event_id, sent_message)
