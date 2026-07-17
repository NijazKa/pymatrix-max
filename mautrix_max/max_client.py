from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import mimetypes
import re
import shutil
import sqlite3
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse

import aiohttp
from pymax import (
    Chat,
    Client,
    ExtraConfig,
    File,
    Message,
    Photo,
    ReactionUpdateEvent,
    Video,
)
from pymax.api.session.enums import DeviceType
from pymax.api.session.payloads import MobileUserAgentPayload
from pymax.config import ANDROID_DEVICES, APP_VERSIONS, LOCALE_TIMEZONES
from pymax.protocol import InboundFrame, Opcode
from pymax.types import AudioAttachment, FileAttachment, PhotoAttachment, VideoAttachment

log = logging.getLogger("mau.max.client")

MessageHandler = Callable[[Message], Awaitable[None]]
ReadyHandler = Callable[[], Awaitable[None]]
ErrorHandler = Callable[[Exception], Awaitable[None]]
ReactionHandler = Callable[[ReactionUpdateEvent], Awaitable[None]]
ChatUpdateHandler = Callable[[Chat], Awaitable[None]]

_DEVICE_PROFILE_FILENAME = "device-profile.json"
_DEVICE_PROFILE_VERSION = 1


def _read_saved_device_ids(work_dir: Path) -> tuple[str | None, str | None]:
    """Read stable device identifiers from an existing PyMax session."""
    session_db = work_dir / "session.db"
    if not session_db.is_file():
        return None, None

    try:
        with sqlite3.connect(str(session_db), timeout=1.0) as db:
            table = db.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='sessions'"
            ).fetchone()
            if table is None:
                return None, None

            columns = {
                row[1] for row in db.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "device_id" not in columns:
                return None, None

            selected = ["device_id"]
            if "mt_instance_id" in columns:
                selected.append("mt_instance_id")
            row = db.execute(
                f"SELECT {', '.join(selected)} FROM sessions LIMIT 1"
            ).fetchone()
    except (OSError, sqlite3.Error) as exc:
        log.warning(
            "Не удалось прочитать идентификаторы устройства из %s: %s",
            session_db,
            exc,
        )
        return None, None

    if row is None:
        return None, None
    device_id = str(row[0] or "") or None
    mt_instance_id = (str(row[1] or "") or None) if len(row) > 1 else None
    return device_id, mt_instance_id


def _used_device_names(profile_path: Path) -> set[str]:
    """Collect device models already assigned to sibling MAX sessions."""
    used: set[str] = set()
    parent = profile_path.parent.parent
    if not parent.is_dir():
        return used

    for other_path in parent.glob(f"*/{_DEVICE_PROFILE_FILENAME}"):
        if other_path == profile_path:
            continue
        try:
            raw = json.loads(other_path.read_text(encoding="utf-8"))
            name = raw.get("user_agent", {}).get("device_name")
            if isinstance(name, str) and name:
                used.add(name)
        except (OSError, ValueError, TypeError):
            continue
    return used


def _generate_device_user_agent(device_id: str, profile_path: Path) -> MobileUserAgentPayload:
    """Create a deterministic, realistic and preferably unique Android profile."""
    digest = hashlib.sha256(device_id.encode("utf-8")).digest()
    used_names = _used_device_names(profile_path)
    start_index = int.from_bytes(digest[0:4], "big") % len(ANDROID_DEVICES)

    selected = ANDROID_DEVICES[start_index]
    for offset in range(len(ANDROID_DEVICES)):
        candidate = ANDROID_DEVICES[(start_index + offset) % len(ANDROID_DEVICES)]
        if candidate[0] not in used_names:
            selected = candidate
            break

    device_name, os_version, screen, arch = selected
    app_version, build_number = APP_VERSIONS[
        int.from_bytes(digest[4:8], "big") % len(APP_VERSIONS)
    ]
    locale, timezone = LOCALE_TIMEZONES[
        int.from_bytes(digest[8:12], "big") % len(LOCALE_TIMEZONES)
    ]

    return MobileUserAgentPayload(
        device_type=DeviceType.ANDROID,
        app_version=app_version,
        os_version=os_version,
        timezone=timezone,
        screen=screen,
        push_device_type="GCM",
        arch=arch,
        locale=locale,
        build_number=build_number,
        device_name=device_name,
        device_locale=locale,
    )


def _write_device_profile(
    profile_path: Path,
    *,
    phone_fingerprint: str,
    device_id: str,
    mt_instance_id: str,
    user_agent: MobileUserAgentPayload,
) -> None:
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _DEVICE_PROFILE_VERSION,
        "phone_sha256": phone_fingerprint,
        "device_id": device_id,
        "mt_instance_id": mt_instance_id,
        "user_agent": user_agent.model_dump(mode="json"),
    }
    temp_path = profile_path.with_suffix(profile_path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.chmod(0o600)
    temp_path.replace(profile_path)
    profile_path.chmod(0o600)


def _load_or_create_device_profile(
    phone: str,
    work_dir: str,
) -> tuple[MobileUserAgentPayload, str, str, Path, bool]:
    """Load a persistent per-account MAX device profile or create it once."""
    work_path = Path(work_dir)
    profile_path = work_path / _DEVICE_PROFILE_FILENAME
    normalized_phone = re.sub(r"\D+", "", phone)
    if len(normalized_phone) == 11 and normalized_phone.startswith("8"):
        normalized_phone = "7" + normalized_phone[1:]
    phone_fingerprint = hashlib.sha256(
        normalized_phone.encode("utf-8")
    ).hexdigest()[:16]
    session_device_id, session_mt_instance_id = _read_saved_device_ids(work_path)
    created = False

    user_agent: MobileUserAgentPayload | None = None
    profile_device_id: str | None = None
    profile_mt_instance_id: str | None = None

    if profile_path.is_file():
        try:
            raw = json.loads(profile_path.read_text(encoding="utf-8"))
            if int(raw.get("version", 0)) != _DEVICE_PROFILE_VERSION:
                raise ValueError("неподдерживаемая версия профиля")
            stored_phone_fingerprint = str(raw.get("phone_sha256") or "")
            if stored_phone_fingerprint != phone_fingerprint:
                raise ValueError("профиль принадлежит другому номеру")
            profile_device_id = str(raw.get("device_id") or "") or None
            profile_mt_instance_id = str(raw.get("mt_instance_id") or "") or None
            user_agent = MobileUserAgentPayload.model_validate(raw.get("user_agent"))
        except (OSError, ValueError, TypeError) as exc:
            log.warning(
                "Профиль MAX-устройства %s не подходит и будет пересоздан: %s",
                profile_path,
                exc,
            )

    # Existing session identifiers are authoritative: changing them may invalidate token login.
    device_id = session_device_id or profile_device_id or str(uuid4())
    mt_instance_id = session_mt_instance_id or profile_mt_instance_id or str(uuid4())

    if user_agent is None:
        user_agent = _generate_device_user_agent(device_id, profile_path)
        created = True

    if (
        created
        or profile_device_id != device_id
        or profile_mt_instance_id != mt_instance_id
    ):
        _write_device_profile(
            profile_path,
            phone_fingerprint=phone_fingerprint,
            device_id=device_id,
            mt_instance_id=mt_instance_id,
            user_agent=user_agent,
        )

    return user_agent, device_id, mt_instance_id, profile_path, created


@dataclass(slots=True)
class DownloadedMaxMedia:
    data: bytes
    filename: str
    mime_type: str
    kind: str
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None

    @property
    def size(self) -> int:
        return len(self.data)


class MaxClientWrapper:
    """Обёртка над одним long-running клиентом PyMax."""

    def __init__(
        self,
        phone: str,
        work_dir: str,
        on_message: MessageHandler,
        on_ready: ReadyHandler | None = None,
        on_error: ErrorHandler | None = None,
        on_reaction_update: ReactionHandler | None = None,
        on_chat_update: ChatUpdateHandler | None = None,
        device_type: str = "DESKTOP",
        app_version: str = "25.12.13",
        sms_code_provider=None,
        password_provider=None,
    ) -> None:
        self.phone = phone
        self.work_dir = work_dir
        self.device_type = device_type
        self.app_version = app_version

        (
            user_agent,
            device_id,
            mt_instance_id,
            self.device_profile_path,
            profile_created,
        ) = _load_or_create_device_profile(phone, work_dir)
        self.device_profile_id = hashlib.sha256(
            device_id.encode("utf-8")
        ).hexdigest()[:12]
        self.device_profile_name = user_agent.device_name

        log.info(
            "Стабильный профиль MAX-устройства: phone=%s profile_id=%s "
            "device_name=%s os=%s app_version=%s created=%s path=%s",
            self.phone,
            self.device_profile_id,
            user_agent.device_name,
            user_agent.os_version,
            user_agent.app_version,
            profile_created,
            self.device_profile_path,
        )

        client_kwargs = {
            "extra_config": ExtraConfig(
                log_level="DEBUG",
                device_id=device_id,
                mt_instance_id=mt_instance_id,
                user_agent=user_agent,
            )
        }
        if sms_code_provider is not None:
            client_kwargs["sms_code_provider"] = sms_code_provider
        if password_provider is not None:
            client_kwargs["password_provider"] = password_provider

        self.client = Client(phone=phone, work_dir=work_dir, **client_kwargs)

        self._on_message_cb = on_message
        self._on_ready_cb = on_ready
        self._on_error_cb = on_error
        self._on_reaction_update_cb = on_reaction_update
        self._on_chat_update_cb = on_chat_update
        self._task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._last_error: Exception | None = None
        self._start_reason = "not-started"
        self._reconnect_count = 0
        self._last_disconnect_reason: str | None = None

        self.client.on_start()(self._handle_start)
        self.client.on_message()(self._handle_message)
        self.client.on_reaction_update()(self._handle_reaction_update)
        self.client.on_chat_update()(self._handle_chat_update)
        self.client.on_raw()(self._handle_raw_frame)
        self.client.on_disconnect()(self._handle_disconnect)

    def _session_diagnostics(self) -> tuple[str, str, bool, int]:
        """Read non-secret diagnostics from PyMax session.db.

        The token itself is never logged. Only the first 12 hex characters of
        its SHA-256 digest are returned, which is enough to correlate token
        rotation or invalidation between lifecycle log records.
        """
        session_db = Path(self.work_dir) / "session.db"
        runtime_device = getattr(
            getattr(getattr(self.client, "_config", None), "device", None),
            "device_id",
            None,
        )
        if not session_db.is_file():
            return "none", str(runtime_device or "unknown"), False, 0

        try:
            with sqlite3.connect(str(session_db), timeout=1.0) as db:
                table = db.execute(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type='table' AND name='sessions'"
                ).fetchone()
                if table is None:
                    return "none", str(runtime_device or "unknown"), False, 0

                columns = {
                    row[1] for row in db.execute("PRAGMA table_info(sessions)").fetchall()
                }
                selected = ["token", "device_id"]
                if "mt_instance_id" in columns:
                    selected.append("mt_instance_id")
                row = db.execute(
                    f"SELECT {', '.join(selected)} FROM sessions LIMIT 1"
                ).fetchone()
                count_row = db.execute("SELECT COUNT(*) FROM sessions").fetchone()
                row_count = int(count_row[0]) if count_row else 0
        except (OSError, sqlite3.Error) as exc:
            log.debug(
                "Не удалось прочитать диагностику PyMax-сессии %s: %s",
                session_db,
                exc,
            )
            return "unreadable", str(runtime_device or "unknown"), False, -1

        if row is None:
            return "none", str(runtime_device or "unknown"), False, row_count

        token = str(row[0] or "")
        token_fingerprint = (
            hashlib.sha256(token.encode("utf-8")).hexdigest()[:12] if token else "none"
        )
        device_id = str(row[1] or runtime_device or "unknown")
        mt_instance_id_set = bool(row[2]) if len(row) > 2 else False
        return token_fingerprint, device_id, mt_instance_id_set, row_count

    async def _handle_disconnect(
        self,
        error: Exception,
        reconnect: bool,
        delay: float,
    ) -> None:
        self._last_disconnect_reason = f"{type(error).__name__}: {error}"
        if reconnect:
            self._reconnect_count += 1

        token_fp, device_id, mt_set, session_rows = self._session_diagnostics()
        log.warning(
            "Соединение PyMax потеряно: phone=%s reason=%s reconnect=%s "
            "delay=%.1fs reconnect_count=%d start_reason=%s token_sha256=%s "
            "device_id=%s mt_instance_id_set=%s session_rows=%d",
            self.phone,
            self._last_disconnect_reason,
            reconnect,
            delay,
            self._reconnect_count,
            self._start_reason,
            token_fp,
            device_id,
            mt_set,
            session_rows,
        )

    @property
    def is_ready(self) -> bool:
        app = getattr(self.client, "_app", None)
        app_started = bool(app and getattr(app, "started", False))
        return bool(
            self._ready.is_set()
            and app_started
            and self._task is not None
            and not self._task.done()
        )

    @property
    def last_error(self) -> Exception | None:
        return self._last_error

    async def _handle_start(self, client: Client) -> None:
        self._last_error = None
        self._ready.set()
        token_fp, device_id, mt_set, session_rows = self._session_diagnostics()
        log.info(
            "PyMax-клиент авторизован: phone=%s start_reason=%s "
            "reconnect_count=%d token_sha256=%s device_id=%s "
            "mt_instance_id_set=%s session_rows=%d device_profile_id=%s "
            "device_name=%s",
            self.phone,
            self._start_reason,
            self._reconnect_count,
            token_fp,
            device_id,
            mt_set,
            session_rows,
            self.device_profile_id,
            self.device_profile_name,
        )

        if self._on_ready_cb is not None:
            try:
                await self._on_ready_cb()
            except Exception:
                log.exception("Не удалось обработать успешный запуск PyMax для %s", self.phone)

    async def _handle_message(self, message: Message, client: Client) -> None:
        try:
            await self._on_message_cb(message)
        except Exception:
            log.exception("Ошибка при обработке входящего сообщения из MAX")

    async def _handle_reaction_update(
        self,
        event: ReactionUpdateEvent,
        client: Client,
    ) -> None:
        log.info(
            "Получено событие реакций MAX: chat=%s message=%s total=%s",
            getattr(event, "chat_id", None),
            getattr(event, "message_id", None),
            getattr(event, "total_count", None),
        )
        if self._on_reaction_update_cb is None:
            return
        try:
            await self._on_reaction_update_cb(event)
        except Exception:
            log.exception("Ошибка при обработке обновления реакций из MAX")

    async def _handle_chat_update(
        self,
        chat: Chat,
        client: Client,
    ) -> None:
        if self._on_chat_update_cb is None:
            return
        try:
            await self._on_chat_update_cb(chat)
        except Exception:
            log.exception(
                "Ошибка при обработке обновления MAX-чата %s",
                getattr(chat, "id", None),
            )

    async def _handle_raw_frame(
        self,
        frame: InboundFrame,
        client: Client,
    ) -> None:
        """Логировать только reaction frame-ы для диагностики push-событий.

        Обработчик не делает сетевых запросов и не реализует polling.
        """
        try:
            opcode = int(frame.opcode)
        except (TypeError, ValueError):
            return

        if opcode not in (
            int(Opcode.NOTIF_MSG_REACTIONS_CHANGED),
            int(Opcode.NOTIF_MSG_YOU_REACTED),
        ):
            return

        log.info(
            "Получен raw MAX reaction frame: opcode=%s cmd=%s payload=%s",
            frame.opcode,
            frame.cmd,
            frame.payload,
        )

    async def start(self, *, reason: str = "unspecified") -> None:
        if self._task is not None and not self._task.done():
            log.debug(
                "PyMax-клиент для %s уже запущен; новый reason=%s проигнорирован",
                self.phone,
                reason,
            )
            return

        self._start_reason = reason
        self._reconnect_count = 0
        self._last_disconnect_reason = None
        self._ready.clear()
        self._last_error = None
        token_fp, device_id, mt_set, session_rows = self._session_diagnostics()
        log.info(
            "Планирую запуск PyMax-клиента: phone=%s reason=%s "
            "token_sha256=%s device_id=%s mt_instance_id_set=%s session_rows=%d",
            self.phone,
            reason,
            token_fp,
            device_id,
            mt_set,
            session_rows,
        )
        self._task = asyncio.create_task(self._run(), name=f"pymax-{self.phone}")

    async def _run(self) -> None:
        log.info(
            "Фоновая задача PyMax запущена: phone=%s reason=%s",
            self.phone,
            self._start_reason,
        )
        try:
            await self.client.start()
            log.info("client.start() штатно завершился для %s", self.phone)
        except asyncio.CancelledError:
            log.debug("Фоновая задача PyMax отменена для %s", self.phone)
            raise
        except Exception as exc:
            self._last_error = exc
            token_fp, device_id, mt_set, session_rows = self._session_diagnostics()
            log.exception(
                "PyMax-клиент завершился с ошибкой: phone=%s start_reason=%s "
                "reconnect_count=%d last_disconnect=%s token_sha256=%s "
                "device_id=%s mt_instance_id_set=%s session_rows=%d",
                self.phone,
                self._start_reason,
                self._reconnect_count,
                self._last_disconnect_reason or "none",
                token_fp,
                device_id,
                mt_set,
                session_rows,
            )
            if self._on_error_cb is not None:
                try:
                    await self._on_error_cb(exc)
                except Exception:
                    log.exception("Не удалось обработать ошибку PyMax для %s", self.phone)
        finally:
            self._ready.clear()

    async def stop(self) -> None:
        self._ready.clear()
        task = self._task
        self._task = None
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        log.info("PyMax-клиент для %s остановлен", self.phone)

    async def logout(self) -> bool:
        result = False
        try:
            if self.is_ready:
                result = await self.client.logout()
                log.info("Сессия MAX для %s завершена на сервере: %s", self.phone, result)
            else:
                log.warning(
                    "PyMax-клиент для %s не готов: выполняю только локальную остановку",
                    self.phone,
                )
            return result
        finally:
            await self.stop()

    def _ensure_ready(self) -> None:
        if self.is_ready:
            return
        if self._last_error is not None:
            raise RuntimeError(f"PyMax-клиент не готов: {self._last_error}") from self._last_error
        raise RuntimeError("PyMax-клиент не авторизован или остановлен")

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: int | None = None,
    ) -> Message | None:
        self._ensure_ready()
        return await self.client.send_message(
            chat_id=chat_id,
            text=text,
            reply_to=reply_to,
        )

    async def send_media(
        self,
        chat_id: int,
        data: bytes,
        filename: str,
        kind: str,
        caption: str = "",
        reply_to: int | None = None,
    ) -> Message | None:
        """Отправить Matrix-медиа в MAX.

        PyMax 2.3.1 поддерживает исходящие Photo/Video/File. Голосовые и
        обычные audio-сообщения отправляются как File: файл воспроизводится,
        но не обязательно отображается в MAX как нативная голосовая заметка.
        """
        self._ensure_ready()
        if kind == "image":
            attachment = Photo(raw=data, name=filename)
        elif kind == "video":
            attachment = Video(raw=data, name=filename)
        else:
            attachment = File(raw=data, name=filename)

        return await self.client.send_message(
            chat_id=chat_id,
            text=caption,
            reply_to=reply_to,
            attachments=[attachment],
        )

    async def add_reaction(
        self,
        chat_id: int,
        message_id: str | int,
        reaction: str,
    ):
        self._ensure_ready()
        try:
            numeric_message_id = int(message_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"MAX message ID должен быть числом, получено: {message_id!r}"
            ) from exc
        return await self.client.add_reaction(
            chat_id=chat_id,
            message_id=numeric_message_id,
            reaction=reaction,
        )

    async def remove_reaction(
        self,
        chat_id: int,
        message_id: str | int,
    ):
        self._ensure_ready()
        try:
            numeric_message_id = int(message_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"MAX message ID должен быть числом, получено: {message_id!r}"
            ) from exc
        return await self.client.remove_reaction(
            chat_id=chat_id,
            message_id=numeric_message_id,
        )

    async def get_reactions(
        self,
        chat_id: int,
        message_ids: list[str | int],
    ):
        self._ensure_ready()
        try:
            numeric_message_ids = [int(message_id) for message_id in message_ids]
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Все MAX message ID должны быть числами: {message_ids!r}"
            ) from exc
        return await self.client.get_reactions(
            chat_id=chat_id,
            message_ids=numeric_message_ids,
        )

    async def get_chat_info(self, chat_id: int):
        self._ensure_ready()
        return await self.client.get_chat(chat_id)

    async def get_known_chats(self, *, refresh: bool = False) -> list:
        """Return chats known to this authenticated account.

        Login already returns a chat list, so normal startup reconciliation is
        free of extra MAX requests. ``refresh=True`` performs one explicit
        CHATS_LIST request and merges its result with the login cache; it is
        intended for the manual ``syncgroups`` command, not for polling.
        """
        self._ensure_ready()
        merged: dict[str, object] = {}
        for chat in self.client.chats or []:
            chat_id = getattr(chat, "id", None)
            if chat_id is not None:
                merged[str(chat_id)] = chat

        if refresh:
            fetched = await self.client.fetch_chats()
            for chat in fetched or []:
                chat_id = getattr(chat, "id", None)
                if chat_id is not None:
                    merged[str(chat_id)] = chat

        return list(merged.values())

    async def resolve_chat_link(self, link: str):
        """Best-effort preview of a MAX group invite link without joining.

        Public channel links are not accepted by ``resolve_group_by_link`` in
        PyMax, so callers should treat ``None`` as "preview unavailable" and
        still try :meth:`join_chat_by_link`.
        """
        self._ensure_ready()
        return await self.client.resolve_group_by_link(link)

    async def join_chat_by_link(self, link: str):
        """Join a MAX group or channel using an invite/public link.

        PyMax's ``join_channel`` accepts both raw channel links and ``join/``
        invite links. Internally both group and channel joining use the same
        CHAT_JOIN opcode, which makes this the generic entry point here.
        """
        self._ensure_ready()
        chat = await self.client.join_channel(link)
        log.info(
            "MAX-аккаунт %s присоединился к чату по ссылке: chat=%s type=%s title=%r",
            self.phone,
            getattr(chat, "id", None),
            getattr(getattr(chat, "type", None), "value", getattr(chat, "type", None)),
            getattr(chat, "title", None),
        )
        return chat

    async def leave_chat(self, chat_id: int, chat_info=None) -> None:
        """Leave a MAX group or channel. Direct dialogs cannot be left."""
        self._ensure_ready()
        chat = chat_info if chat_info is not None else await self.client.get_chat(chat_id)
        chat_type = getattr(chat, "type", None)
        type_value = str(getattr(chat_type, "value", chat_type) or "").upper()
        if type_value in {"DIALOG", "DIRECT", "DM"}:
            raise RuntimeError("Cannot leave a direct MAX dialog")

        leave = getattr(chat, "leave", None)
        if callable(leave):
            await leave()
        elif type_value == "CHANNEL":
            await self.client.leave_channel(chat_id)
        else:
            await self.client.leave_group(chat_id)

        log.info(
            "MAX-аккаунт %s вышел из чата %s type=%s",
            self.phone,
            chat_id,
            type_value or "unknown",
        )

    async def get_user_info(self, user_id: int):
        self._ensure_ready()
        return await self.client.get_user(user_id)

    async def get_me(self):
        self._ensure_ready()
        return self.client.me

    @staticmethod
    def _normalise_url(url: str) -> str:
        if url.startswith("//"):
            return "https:" + url
        return url

    @staticmethod
    def _extension_for(mime_type: str, fallback: str) -> str:
        mime_type = mime_type.split(";", 1)[0].strip().lower()
        preferred = {
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/quicktime": ".mov",
            "video/3gpp": ".3gp",
            "video/mp2t": ".ts",
            "video/mpeg": ".mpeg",
            "video/x-msvideo": ".avi",
            "audio/ogg": ".ogg",
            "audio/mpeg": ".mp3",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
        }
        return preferred.get(mime_type) or mimetypes.guess_extension(mime_type) or fallback

    @staticmethod
    def _sniff_media_mime(data: bytes) -> str | None:
        """Определить контейнер по сигнатуре, не доверяя CDN Content-Type."""
        if not data:
            return None

        head = data[:4096]
        stripped = head.lstrip(b"\xef\xbb\xbf\x00\t\r\n ")
        lower = stripped[:256].lower()

        # ISO Base Media File Format: MP4/MOV/3GP.
        if len(head) >= 12 and head[4:8] == b"ftyp":
            brand = head[8:12].lower()
            if brand == b"qt  ":
                return "video/quicktime"
            if brand.startswith((b"3gp", b"3g2")):
                return "video/3gpp"
            return "video/mp4"

        # Matroska/WebM (EBML).
        if head.startswith(b"\x1a\x45\xdf\xa3"):
            return "video/webm" if b"webm" in head.lower() else "video/x-matroska"

        if head.startswith(b"RIFF") and head[8:12] == b"AVI ":
            return "video/x-msvideo"
        if head.startswith(b"FLV"):
            return "video/x-flv"
        if head.startswith(b"OggS"):
            return "application/ogg"
        if head.startswith(b"ID3") or head[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
            return "audio/mpeg"
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if head.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if head.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
            return "image/webp"

        # MPEG transport/program streams.
        if head.startswith(b"\x00\x00\x01\xba"):
            return "video/mpeg"
        if len(head) >= 377 and head[0] == 0x47 and head[188] == 0x47 and head[376] == 0x47:
            return "video/mp2t"

        if lower.startswith(b"#extm3u"):
            return "application/vnd.apple.mpegurl"

        # MPEG-DASH manifests are XML documents. Do not classify every XML
        # response as HTML: MAX video endpoints commonly return an MPD here.
        xml_head = head.lower()
        if lower.startswith(b"<?xml") or b"<mpd" in xml_head:
            if b"<mpd" in xml_head or b"urn:mpeg:dash:schema:mpd" in xml_head:
                return "application/dash+xml"
            return "application/xml"

        if lower.startswith((b"<!doctype html", b"<html")):
            return "text/html"
        if lower.startswith((b"{", b"[")):
            return "application/json"
        return None

    @classmethod
    def _select_media_mime(
        cls,
        data: bytes,
        declared_mime: str,
        fallback_mime: str,
    ) -> tuple[str, str | None]:
        declared = (declared_mime or "").split(";", 1)[0].strip().lower()
        fallback = fallback_mime.split(";", 1)[0].strip().lower()
        detected = cls._sniff_media_mime(data)

        generic = {
            "",
            "application/octet-stream",
            "binary/octet-stream",
            "application/download",
            "application/x-download",
        }
        if detected:
            # Сигнатура надёжнее generic Content-Type CDN. Также не позволяем
            # HTML/JSON/HLS маскироваться под video/mp4 из fallback.
            if declared in generic or detected.startswith(("video/", "audio/", "image/")):
                return detected, detected
            if detected in {
                "application/vnd.apple.mpegurl",
                "application/dash+xml",
                "application/xml",
                "application/json",
                "text/html",
            }:
                return detected, detected

        return (declared if declared not in generic else fallback), detected

    async def _download_url(
        self,
        url: str,
        *,
        filename: str,
        fallback_mime: str,
        max_size: int,
    ) -> tuple[bytes, str, str]:
        url = self._normalise_url(url)
        proxy = None
        app = getattr(self.client, "_app", None)
        config = getattr(app, "config", None)
        if config is not None:
            proxy = getattr(config, "proxy", None)

        timeout = aiohttp.ClientTimeout(total=900, sock_connect=30, sock_read=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, proxy=proxy) as response:
                response.raise_for_status()
                declared_size = response.content_length
                if declared_size is not None and declared_size > max_size:
                    raise ValueError(
                        f"Медиа MAX слишком большое: {declared_size} байт, лимит {max_size}"
                    )

                declared_mime = response.headers.get("Content-Type", "")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.content.iter_chunked(1024 * 1024):
                    total += len(chunk)
                    if total > max_size:
                        raise ValueError(
                            f"Медиа MAX превысило лимит {max_size} байт при скачивании"
                        )
                    chunks.append(chunk)

        data = b"".join(chunks)
        mime_type, detected_mime = self._select_media_mime(
            data,
            declared_mime,
            fallback_mime,
        )

        parsed_url = urlparse(url)
        log.info(
            "MAX media downloaded: host=%s path=%s size=%d "
            "declared_mime=%s detected_mime=%s selected_mime=%s signature=%s",
            parsed_url.hostname or "unknown",
            parsed_url.path or "/",
            len(data),
            declared_mime or "none",
            detected_mime or "unknown",
            mime_type,
            data[:16].hex(),
        )

        if mime_type in {
            "application/vnd.apple.mpegurl",
            "application/x-mpegurl",
        }:
            raise ValueError(
                "MAX вернул HLS-плейлист вместо готового видеофайла; "
                "такой поток нельзя загружать в Matrix как MP4"
            )
        if mime_type in {"text/html", "application/json"}:
            raise ValueError(
                f"MAX CDN вернул служебный ответ {mime_type} вместо медиафайла"
            )

        expected_extension = self._extension_for(mime_type, ".bin")
        path = Path(filename)
        if not path.suffix:
            filename += expected_extension
        elif mime_type.startswith("video/") and path.suffix.lower() != expected_extension:
            filename = str(path.with_suffix(expected_extension))

        return data, filename, mime_type

    @staticmethod
    def _sanitise_ffmpeg_error(stderr: bytes) -> str:
        text = stderr.decode("utf-8", errors="replace")
        # CDN URLs contain short-lived signatures in both query and path.
        # Never copy them into bridge logs.
        text = re.sub(r"https?://[^\s\"']+", "<redacted-url>", text)
        return " ".join(text.strip().split())[-1200:]

    async def _download_dash_to_mp4(
        self,
        url: str,
        *,
        filename: str,
        max_size: int,
    ) -> tuple[bytes, str, str]:
        """Download a MAX MPEG-DASH stream and remux it into a normal MP4."""
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError(
                "MAX вернул MPEG-DASH video, но ffmpeg не установлен в контейнере"
            )

        url = self._normalise_url(url)
        parsed_url = urlparse(url)
        started = time.monotonic()

        with tempfile.TemporaryDirectory(prefix="mautrix-max-dash-") as temp_dir:
            output_path = Path(temp_dir) / "video.mp4"
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
            ]
            if parsed_url.scheme in {"http", "https"}:
                command.extend([
                    "-reconnect",
                    "1",
                    "-reconnect_streamed",
                    "1",
                    "-reconnect_delay_max",
                    "5",
                ])
            command.extend([
                "-i",
                url,
                "-map",
                "0:v:0?",
                "-map",
                "0:a:0?",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output_path),
            ])

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            limit_exceeded = False

            async def watch_output_size() -> None:
                nonlocal limit_exceeded
                while process.returncode is None:
                    await asyncio.sleep(0.25)
                    try:
                        current_size = output_path.stat().st_size
                    except FileNotFoundError:
                        continue
                    if current_size > max_size:
                        limit_exceeded = True
                        process.kill()
                        return

            watcher = asyncio.create_task(watch_output_size())
            try:
                try:
                    _, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=900,
                    )
                except asyncio.TimeoutError as exc:
                    process.kill()
                    _, stderr = await process.communicate()
                    raise TimeoutError(
                        "Сборка MPEG-DASH видео MAX превысила таймаут 900 секунд"
                    ) from exc
            finally:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)

            if limit_exceeded:
                raise ValueError(
                    f"Видео MAX превысило лимит {max_size} байт при сборке DASH"
                )
            if process.returncode != 0:
                details = self._sanitise_ffmpeg_error(stderr)
                raise ValueError(
                    "ffmpeg не смог собрать MPEG-DASH видео MAX "
                    f"(exit={process.returncode}): {details or 'без текста ошибки'}"
                )
            if not output_path.is_file():
                raise ValueError("ffmpeg завершился без выходного MP4-файла")

            size = output_path.stat().st_size
            if size <= 0:
                raise ValueError("ffmpeg создал пустой MP4-файл")
            if size > max_size:
                raise ValueError(
                    f"Собранное видео MAX слишком большое: {size} байт, лимит {max_size}"
                )

            data = output_path.read_bytes()

        detected = self._sniff_media_mime(data)
        if detected != "video/mp4":
            raise ValueError(
                "ffmpeg собрал неожиданный контейнер вместо MP4: "
                f"{detected or 'не определён'}"
            )

        filename = str(Path(filename).with_suffix(".mp4"))
        log.info(
            "MAX DASH video remuxed: host=%s size=%d elapsed=%.1fs",
            parsed_url.hostname or "unknown",
            len(data),
            time.monotonic() - started,
        )
        return data, filename, "video/mp4"

    async def download_attachment(
        self,
        message: Message,
        attachment,
        *,
        max_size: int,
    ) -> DownloadedMaxMedia | None:
        """Скачать поддерживаемое вложение MAX для загрузки в Matrix."""
        self._ensure_ready()
        if message.chat_id is None:
            return None

        if isinstance(attachment, PhotoAttachment):
            filename = f"max_photo_{attachment.photo_id}.jpg"
            data, filename, mime = await self._download_url(
                attachment.base_url,
                filename=filename,
                fallback_mime="image/jpeg",
                max_size=max_size,
            )
            return DownloadedMaxMedia(
                data=data,
                filename=filename,
                mime_type=mime,
                kind="image",
                width=attachment.width,
                height=attachment.height,
            )

        if isinstance(attachment, VideoAttachment):
            request = await self.client.get_video_by_id(
                message.chat_id,
                message.id,
                attachment.video_id,
            )
            if request is None or not request.url:
                return None
            filename = f"max_video_{attachment.video_id}.mp4"
            data, filename, mime = await self._download_url(
                request.url,
                filename=filename,
                fallback_mime="video/mp4",
                max_size=max_size,
            )
            if mime == "application/dash+xml" or (
                mime == "application/xml"
                and urlparse(request.url).path.lower().endswith(".mpd")
            ):
                data, filename, mime = await self._download_dash_to_mp4(
                    request.url,
                    filename=filename,
                    max_size=max_size,
                )
            return DownloadedMaxMedia(
                data=data,
                filename=filename,
                mime_type=mime,
                kind="video",
                width=attachment.width,
                height=attachment.height,
                duration_ms=attachment.duration,
            )

        if isinstance(attachment, AudioAttachment):
            if not attachment.url:
                return None
            audio_id = attachment.audio_id or message.id
            filename = f"max_voice_{audio_id}.ogg"
            data, filename, mime = await self._download_url(
                attachment.url,
                filename=filename,
                fallback_mime="audio/ogg",
                max_size=max_size,
            )
            return DownloadedMaxMedia(
                data=data,
                filename=filename,
                mime_type=mime,
                kind="audio",
                duration_ms=attachment.duration,
            )

        if isinstance(attachment, FileAttachment):
            request = await self.client.get_file_by_id(
                message.chat_id,
                message.id,
                attachment.file_id,
            )
            if request is None or not request.url:
                return None
            filename = attachment.name or f"max_file_{attachment.file_id}"
            fallback = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            data, filename, mime = await self._download_url(
                request.url,
                filename=filename,
                fallback_mime=fallback,
                max_size=max_size,
            )
            return DownloadedMaxMedia(
                data=data,
                filename=filename,
                mime_type=mime,
                kind="file",
            )

        return None
