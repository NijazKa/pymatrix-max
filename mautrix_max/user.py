from __future__ import annotations

import asyncio
import logging
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from mautrix.bridge import BaseUser
from mautrix.types import RoomID, UserID

from . import db as db_module
from .max_auth_providers import BridgePasswordProvider, BridgeSmsCodeProvider
from .max_client import MaxClientWrapper

log = logging.getLogger("mau.user")


class User(BaseUser):
    by_mxid: dict[UserID, "User"] = {}

    # Назначаются мостом в prepare_config()/prepare_bridge().
    config = None
    bridge = None
    az = None
    loop = None

    max_client: MaxClientWrapper | None = None
    max_phone: str | None = None
    _db_row: db_module.User | None = None

    def __init__(self, mxid: UserID) -> None:
        self.mxid = mxid
        self.management_room: RoomID | None = None

        super().__init__()

        self.max_client = None
        self.command_status: dict[str, Any] | None = None
        self._pending_input: asyncio.Future[str] | None = None
        self._login_in_progress = False
        self._blocked_leave_attempts: dict[str, float] = {}
        self._explicit_chat_joins: set[str] = set()

        (
            self.permission_level,
            self.relay_whitelisted,
            self.is_whitelisted,
            self.is_admin,
        ) = self.config.get_permissions(mxid)

    @classmethod
    async def get_by_mxid(cls, mxid: UserID, create: bool = True) -> "User | None":
        if mxid in cls.by_mxid:
            return cls.by_mxid[mxid]

        row = await db_module.User.get_by_mxid(mxid)
        user = cls(mxid)

        if row:
            user._db_row = row
            user.max_phone = row.max_phone
            user.management_room = row.management_room
        elif create:
            user._db_row = db_module.User(
                db=db_module.User.db,
                mxid=mxid,
                max_phone=None,
                max_session_file=None,
                management_room=None,
            )
            await user._db_row.insert()
        else:
            return None

        cls.by_mxid[mxid] = user
        return user

    @classmethod
    async def all_logged_in(cls) -> list["User"]:
        rows = await db_module.User.all_logged_in()
        users: list[User] = []

        for row in rows:
            user = cls.by_mxid.get(row.mxid) or cls(row.mxid)
            user._db_row = row
            user.max_phone = row.max_phone
            user.management_room = row.management_room
            cls.by_mxid[row.mxid] = user
            users.append(user)

        return users

    async def is_logged_in(self) -> bool:
        """Проверить реальную готовность PyMax, а не наличие объекта."""
        return bool(self.max_client and self.max_client.is_ready)

    async def get_puppet(self):
        """Double puppeting пока не поддерживается."""
        return None

    async def get_portal_with(self, other_user: "User", create: bool = True):
        """Прямые чаты между Matrix-пользователями моста не поддерживаются."""
        return None

    @staticmethod
    def _chat_is_direct(chat) -> bool:
        is_dialog = getattr(chat, "is_dialog", None)
        if isinstance(is_dialog, bool):
            return is_dialog
        chat_type = getattr(chat, "type", None)
        value = getattr(chat_type, "value", chat_type)
        return str(value or "").upper() in {"DIALOG", "DIRECT", "DM"}

    @staticmethod
    def _chat_membership_status(chat) -> str:
        """Return a normalized MAX membership status for a chat."""
        status = getattr(chat, "status", None)
        value = getattr(status, "value", status)
        return str(value or "").strip().upper()

    @classmethod
    def _chat_is_active_member(cls, chat) -> bool:
        """Whether the current MAX account is an active chat member.

        MAX keeps channels/groups in the chat list for some time after leave,
        but marks them inactive. Treating those rows as active caused startup
        reconciliation to invite the Matrix user back into an old portal.
        Missing status is accepted for backwards compatibility; any explicit
        status must be ACTIVE.
        """
        status = cls._chat_membership_status(chat)
        return not status or status == "ACTIVE"

    async def sync_group_portal_by_chat_id(self, chat_id: str) -> dict[str, object]:
        """Verify one shared MAX chat by exact ID and ensure Matrix access.

        This targeted path is intended for old or quiet chats that are absent
        from the limited login/CHATS_LIST cache. It performs exactly one
        ``get_chat`` request and therefore avoids scanning or polling.
        """
        from .portal import Portal

        wrapper = self.max_client
        if wrapper is None or not wrapper.is_ready:
            raise RuntimeError("MAX-клиент не готов")

        chat_id = str(chat_id).strip()
        try:
            numeric_chat_id = int(chat_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Некорректный MAX chat ID: {chat_id!r}") from exc

        if await db_module.BlockedChat.is_blocked(self.mxid, chat_id):
            return {
                "chat_id": chat_id,
                "blocked": True,
                "created": False,
                "invited": False,
                "room_id": None,
                "name": None,
            }

        chat = await wrapper.get_chat_info(numeric_chat_id)
        if self._chat_is_direct(chat):
            raise ValueError("Указанный chat ID относится к личному диалогу")

        status = self._chat_membership_status(chat)
        if not self._chat_is_active_member(chat):
            portal = await Portal.get_by_chat_id(
                chat_id=chat_id,
                receiver=self.mxid,
                create=False,
                is_direct=False,
            )
            removed = await db_module.PortalUser.remove(chat_id, self.mxid)
            log.info(
                "Точная синхронизация: MAX-аккаунт не состоит в чате; "
                "Matrix-связь удалена: mxid=%s phone=%s chat=%s room=%s "
                "status=%s removed=%s",
                self.mxid,
                self.max_phone,
                chat_id,
                portal.mxid if portal else None,
                status or "UNKNOWN",
                removed,
            )
            return {
                "chat_id": chat_id,
                "blocked": False,
                "active": False,
                "status": status,
                "created": False,
                "invited": False,
                "room_id": portal.mxid if portal else None,
                "name": (getattr(chat, "title", None) or (portal.name if portal else None)),
            }

        portal = await Portal.get_by_chat_id(
            chat_id=chat_id,
            receiver=self.mxid,
            create=True,
            is_direct=False,
        )
        if portal is None:
            raise RuntimeError("Не удалось создать или открыть portal")

        title = getattr(chat, "title", None)
        if title:
            portal.name = title
        portal.is_direct = False
        await portal.save()

        created = portal.mxid is None
        if created:
            await portal.create_matrix_room(source=self, chat_info=chat)
            invited = True
        else:
            invited = await portal.ensure_matrix_user(
                self.mxid,
                reason="Точная синхронизация участия в MAX-группе или канале",
            )

        log.info(
            "Точная синхронизация общего MAX portal: mxid=%s phone=%s "
            "chat=%s room=%s created=%s invite_checked=%s status=%r",
            self.mxid,
            self.max_phone,
            chat_id,
            portal.mxid,
            created,
            invited,
            getattr(chat, "status", None),
        )
        return {
            "chat_id": chat_id,
            "blocked": False,
            "active": True,
            "status": status,
            "created": created,
            "invited": invited,
            "room_id": portal.mxid,
            "name": portal.name,
        }

    async def sync_group_portals(self, *, refresh: bool = False) -> dict[str, int]:
        """Associate this account with existing shared group/channel portals.

        The normal startup path uses the chat list already returned by MAX
        during LOGIN and therefore performs no additional remote request. The
        manual ``syncgroups`` command may request one explicit refresh.
        """
        from .portal import Portal

        stats = {
            "known": 0,
            "portals": 0,
            "associated": 0,
            "blocked": 0,
            "inactive": 0,
        }
        wrapper = self.max_client
        if wrapper is None or not wrapper.is_ready:
            return stats

        chats = await wrapper.get_known_chats(refresh=refresh)
        for chat in chats:
            chat_id_value = getattr(chat, "id", None)
            if chat_id_value is None or self._chat_is_direct(chat):
                continue

            chat_id = str(chat_id_value)
            stats["known"] += 1
            status = self._chat_membership_status(chat)
            if not self._chat_is_active_member(chat):
                stats["inactive"] += 1
                removed = await db_module.PortalUser.remove(chat_id, self.mxid)
                if removed:
                    log.info(
                        "Удалена устаревшая связь с неактивным MAX-чатом: "
                        "mxid=%s phone=%s chat=%s status=%s",
                        self.mxid,
                        self.max_phone,
                        chat_id,
                        status or "UNKNOWN",
                    )
                continue

            if await db_module.BlockedChat.is_blocked(self.mxid, chat_id):
                stats["blocked"] += 1
                await db_module.PortalUser.remove(chat_id, self.mxid)
                continue

            portal = await Portal.get_by_chat_id(
                chat_id=chat_id,
                receiver=self.mxid,
                create=False,
                is_direct=False,
            )
            if portal is None:
                # Do not create a Matrix room or even a portal row for every
                # remote chat at login. Existing bridge portals are reconciled;
                # new rooms are still created by chat updates/messages/join.
                continue

            stats["portals"] += 1
            title = getattr(chat, "title", None)
            if title and portal.name != title:
                portal.name = title
                await portal.save()

            await portal.ensure_matrix_user(
                self.mxid,
                reason="Синхронизация участия в MAX-группе или канале",
            )
            stats["associated"] += 1

        log.info(
            "Синхронизация общих MAX portal: mxid=%s phone=%s refresh=%s "
            "known=%d portals=%d associated=%d blocked=%d inactive=%d",
            self.mxid,
            self.max_phone,
            refresh,
            stats["known"],
            stats["portals"],
            stats["associated"],
            stats["blocked"],
            stats["inactive"],
        )
        return stats

    def _bot_intent(self):
        """Получить intent bridge-бота независимо от версии BaseUser."""
        if self.bridge is not None and getattr(self.bridge, "az", None) is not None:
            return self.bridge.az.intent

        if self.az is not None:
            return self.az.intent

        raise RuntimeError("User не привязан к экземпляру MaxBridge")

    async def remember_management_room(self, room_id: RoomID) -> None:
        """Persist the user's management room for asynchronous auth alerts."""
        room_id = RoomID(room_id)
        if self.management_room == room_id and (
            self._db_row is None or self._db_row.management_room == room_id
        ):
            return

        self.management_room = room_id
        if self._db_row is not None:
            self._db_row.management_room = room_id
            await self._db_row.save()

    def _max_session_work_dir(self) -> str:
        """Постоянный каталог сессии PyMax для Matrix-пользователя."""
        session_root = self.config["bridge.max.session_dir"] or "./sessions"
        safe_mxid = quote(str(self.mxid), safe="")
        return str(Path(session_root) / safe_mxid)

    def _clear_max_session_data(self) -> None:
        """Delete PyMax auth/cache data while preserving the stable device profile."""
        work_dir = Path(self._max_session_work_dir())
        profile_path = work_dir / "device-profile.json"
        profile_data: bytes | None = None

        try:
            if profile_path.is_file():
                profile_data = profile_path.read_bytes()
        except OSError:
            log.exception(
                "Не удалось сохранить профиль MAX-устройства перед очисткой %s",
                work_dir,
            )

        shutil.rmtree(work_dir, ignore_errors=True)

        if profile_data is not None:
            try:
                work_dir.mkdir(parents=True, exist_ok=True)
                profile_path.write_bytes(profile_data)
                profile_path.chmod(0o600)
            except OSError:
                log.exception(
                    "Не удалось восстановить профиль MAX-устройства в %s",
                    work_dir,
                )

    def _has_saved_session(self) -> bool:
        """Проверить, что session.db существует и содержит токен."""
        session_db = Path(self._max_session_work_dir()) / "session.db"
        if not session_db.is_file():
            return False

        try:
            with sqlite3.connect(session_db) as db:
                table = db.execute(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type='table' AND name='sessions'"
                ).fetchone()
                if table is None:
                    return False

                row = db.execute("SELECT COUNT(*) FROM sessions").fetchone()
                return bool(row and row[0] > 0)
        except sqlite3.Error:
            log.exception("Не удалось проверить PyMax-сессию %s", session_db)
            return False

    # --- Ожидание кода или пароля из Matrix ---

    async def wait_for_input(self, prompt: str) -> str:
        management_room = self.management_room
        if not management_room:
            raise RuntimeError(
                f"У пользователя {self.mxid} нет management-комнаты, "
                "не могу запросить ввод"
            )

        if self._pending_input is not None and not self._pending_input.done():
            raise RuntimeError("Мост уже ожидает код или пароль")

        loop = asyncio.get_running_loop()
        pending_input: asyncio.Future[str] = loop.create_future()
        self._pending_input = pending_input

        # Устанавливаем command_status до отправки notice, чтобы быстрый ответ
        # пользователя не превратился в Unknown command.
        self.command_status = {
            "next": self._resolve_pending_input,
            "action": "Max login",
        }

        try:
            await self._bot_intent().send_notice(management_room, prompt)
            return await pending_input
        finally:
            if self._pending_input is pending_input:
                self._pending_input = None
                self.command_status = None

    async def _resolve_pending_input(self, evt) -> None:
        """Получить следующее сообщение как SMS-код или 2FA-пароль."""
        pending_input = self._pending_input
        if pending_input is None or pending_input.done():
            return

        args = list(getattr(evt, "args", None) or [])
        if not args:
            command = getattr(evt, "command", None)
            if command:
                args.append(str(command))

        value = " ".join(str(part) for part in args).strip()
        if not value:
            await evt.reply("Получено пустое значение. Введите его ещё раз.")
            return

        # Само значение намеренно не пишем в лог: это может быть 2FA-пароль.
        log.info(
            "Получен ввод для авторизации: mxid=%s, room=%s, length=%d",
            self.mxid,
            getattr(evt, "room_id", None),
            len(value),
        )
        pending_input.set_result(value)

    async def cancel_pending_login(self) -> None:
        self._login_in_progress = False

        if self._pending_input is not None and not self._pending_input.done():
            self._pending_input.cancel()

        self.command_status = None
        self._pending_input = None

        if self.max_client is not None:
            await self.max_client.stop()
            self.max_client = None

        # Незавершённая попытка могла создать пустой session.db.
        self._clear_max_session_data()

    # --- События состояния PyMax ---

    async def handle_max_ready(self) -> None:
        """Сохранить успешный вход и уведомить management-комнату."""
        manual_login = self._login_in_progress
        self._login_in_progress = False

        if self.max_client is not None:
            self.max_phone = self.max_client.phone

        if self._db_row is not None:
            self._db_row.max_phone = self.max_phone
            self._db_row.max_session_file = str(
                Path(self._max_session_work_dir()) / "session.db"
            )
            await self._db_row.save()

        try:
            await self.sync_group_portals(refresh=False)
        except Exception:
            log.exception(
                "Не удалось синхронизировать общие MAX portal после входа: mxid=%s",
                self.mxid,
            )

        if not manual_login:
            # При обычном восстановлении сессии после рестарта не засоряем чат.
            return

        if not self.management_room:
            log.warning(
                "PyMax успешно авторизован для %s, но management-комната не задана",
                self.mxid,
            )
            return

        await self._bot_intent().send_notice(
            self.management_room,
            "Авторизация в MAX успешно завершена. "
            "Мост подключён и готов принимать и отправлять сообщения.",
        )

    async def handle_max_error(self, error: Exception) -> None:
        """Handle a terminal PyMax error and alert the user when auth expires."""
        manual_login = self._login_in_progress
        self._login_in_progress = False
        error_text = str(error)
        phone = self.max_client.phone if self.max_client is not None else self.max_phone
        token_invalid = "FAIL_LOGIN_TOKEN" in error_text

        if token_invalid:
            # The server has explicitly rejected this token. Keep the management
            # room, but remove unusable auth state so restarts don't loop forever.
            self._clear_max_session_data()
            self.max_phone = None
            if self._db_row is not None:
                self._db_row.max_phone = None
                self._db_row.max_session_file = None
                await self._db_row.save()

            notice = (
                f"Сессия MAX для {phone or 'аккаунта'} завершена сервером: "
                "токен входа больше недействителен (`FAIL_LOGIN_TOKEN`). "
                "Выполните повторный вход командой "
                f"`login {phone}` в этой комнате."
                if phone
                else
                "Сессия MAX завершена сервером: токен входа больше "
                "недействителен (`FAIL_LOGIN_TOKEN`). Выполните повторный "
                "вход командой `login <телефон>` в этой комнате."
            )

            if self.management_room:
                try:
                    await self._bot_intent().send_notice(self.management_room, notice)
                except Exception:
                    log.exception(
                        "Не удалось уведомить %s в management-комнате %s "
                        "об истёкшей MAX-сессии",
                        self.mxid,
                        self.management_room,
                    )
            else:
                log.warning(
                    "MAX-токен отклонён для mxid=%s phone=%s, но management-комната "
                    "не сохранена. Выполните ping или login в комнате бота после обновления.",
                    self.mxid,
                    phone,
                )
            return

        if manual_login and self.management_room:
            await self._bot_intent().send_notice(
                self.management_room,
                "Авторизация в MAX не завершена: " + error_text,
            )

    # --- Логин и восстановление сессии ---

    async def request_login_code(
        self,
        phone: str,
        management_room: RoomID,
    ) -> None:
        """Начать принудительную чистую авторизацию в MAX."""
        await self.remember_management_room(management_room)

        if self.max_client is not None:
            await self.max_client.stop()
            self.max_client = None

        work_dir = self._max_session_work_dir()

        # Команда login всегда означает новую авторизацию. Это исключает
        # повторное использование протухшего токена FAIL_LOGIN_TOKEN и сессии
        # от ранее введённого другого номера.
        self._clear_max_session_data()

        self.max_phone = phone
        self._login_in_progress = True

        self.max_client = MaxClientWrapper(
            phone=phone,
            work_dir=work_dir,
            on_message=self.handle_max_message,
            on_ready=self.handle_max_ready,
            on_error=self.handle_max_error,
            on_reaction_update=self.handle_max_reaction_update,
            on_chat_update=self.handle_max_chat_update,
            sms_code_provider=BridgeSmsCodeProvider(self),
            password_provider=BridgePasswordProvider(self),
        )
        await self.max_client.start(reason="manual-login")

    async def start_max_client(self) -> None:
        """Восстановить сохранённую сессию после запуска моста."""
        if not self.max_phone:
            return

        if self.max_client is not None:
            if self.max_client.is_ready:
                return
            await self.max_client.stop()
            self.max_client = None

        if not self._has_saved_session():
            log.warning(
                "Сохранённая сессия PyMax для %s не найдена в %s. "
                "Выполните !max login заново.",
                self.mxid,
                self._max_session_work_dir(),
            )
            return

        self._login_in_progress = False
        self.max_client = MaxClientWrapper(
            phone=self.max_phone,
            work_dir=self._max_session_work_dir(),
            on_message=self.handle_max_message,
            on_ready=self.handle_max_ready,
            on_error=self.handle_max_error,
            on_reaction_update=self.handle_max_reaction_update,
            on_chat_update=self.handle_max_chat_update,
            sms_code_provider=BridgeSmsCodeProvider(self),
            password_provider=BridgePasswordProvider(self),
        )
        await self.max_client.start(reason="restore-saved-session")

    async def logout(self) -> None:
        """Завершить серверную сессию и удалить локальные данные входа."""
        self._login_in_progress = False

        if self._pending_input is not None and not self._pending_input.done():
            self._pending_input.cancel()
        self._pending_input = None
        self.command_status = None

        try:
            if self.max_client is not None:
                await self.max_client.logout()
        finally:
            self.max_client = None
            self._clear_max_session_data()

            self.max_phone = None
            if self._db_row is not None:
                self._db_row.max_phone = None
                self._db_row.max_session_file = None
                await self._db_row.save()

    # --- Local denylist for unwanted MAX groups/channels ---

    async def block_chat(self, chat_id: str, name: str | None = None) -> None:
        chat_id = str(chat_id)
        await db_module.BlockedChat.add(self.mxid, chat_id, name)
        await db_module.PortalUser.remove(chat_id, self.mxid)
        self._blocked_leave_attempts.pop(chat_id, None)

    def mark_blocked_leave_attempt(self, chat_id: str) -> None:
        self._blocked_leave_attempts[str(chat_id)] = time.monotonic()

    def clear_blocked_leave_attempt(self, chat_id: str) -> None:
        self._blocked_leave_attempts.pop(str(chat_id), None)

    async def unblock_chat(self, chat_id: str) -> bool:
        self._blocked_leave_attempts.pop(str(chat_id), None)
        return await db_module.BlockedChat.remove(self.mxid, str(chat_id))

    async def get_blocked_chats(self) -> list[db_module.BlockedChat]:
        return await db_module.BlockedChat.get_all(self.mxid)

    def begin_explicit_chat_join(self, chat_id: str) -> None:
        """Temporarily suppress denylist auto-leave during an explicit join."""
        self._explicit_chat_joins.add(str(chat_id))

    def end_explicit_chat_join(self, chat_id: str) -> None:
        self._explicit_chat_joins.discard(str(chat_id))

    async def _handle_blocked_chat_event(
        self,
        chat_id: str,
        *,
        event_kind: str,
        chat_info=None,
    ) -> bool:
        """Ignore a blocked chat and periodically retry leaving it.

        The check is event-driven. There is no polling. A five-minute throttle
        prevents a burst of service events from causing repeated leave calls.
        """
        chat_id = str(chat_id)
        if chat_id in self._explicit_chat_joins:
            log.debug(
                "Событие MAX-чата разрешено во время явного join: mxid=%s chat=%s event=%s",
                self.mxid,
                chat_id,
                event_kind,
            )
            return False

        if not await db_module.BlockedChat.is_blocked(self.mxid, chat_id):
            return False

        await db_module.PortalUser.remove(chat_id, self.mxid)
        now = time.monotonic()
        last_attempt = self._blocked_leave_attempts.get(chat_id)
        should_leave = last_attempt is None or now - last_attempt >= 300
        if should_leave and self.max_client is not None and self.max_client.is_ready:
            self._blocked_leave_attempts[chat_id] = now
            try:
                await self.max_client.leave_chat(int(chat_id), chat_info=chat_info)
            except Exception:
                log.exception(
                    "Автоматический выход из заблокированного MAX-чата не удался: "
                    "mxid=%s phone=%s chat=%s event=%s",
                    self.mxid,
                    self.max_phone,
                    chat_id,
                    event_kind,
                )
            else:
                log.info(
                    "Автоматически вышел из заблокированного MAX-чата: "
                    "mxid=%s phone=%s chat=%s event=%s",
                    self.mxid,
                    self.max_phone,
                    chat_id,
                    event_kind,
                )
        else:
            log.debug(
                "Событие заблокированного MAX-чата пропущено: "
                "mxid=%s chat=%s event=%s leave_throttled=%s",
                self.mxid,
                chat_id,
                event_kind,
                not should_leave,
            )

        return True

    async def handle_max_chat_update(self, chat) -> None:
        from .portal import Portal

        chat_id_value = getattr(chat, "id", None)
        if chat_id_value is None:
            return
        chat_id = str(chat_id_value)
        if await self._handle_blocked_chat_event(
            chat_id,
            event_kind="chat_update",
            chat_info=chat,
        ):
            return

        if self._chat_is_direct(chat):
            return

        if not self._chat_is_active_member(chat):
            removed = await db_module.PortalUser.remove(chat_id, self.mxid)
            log.info(
                "MAX chat_update сообщает, что аккаунт больше не состоит в чате: "
                "mxid=%s phone=%s chat=%s status=%s removed=%s",
                self.mxid,
                self.max_phone,
                chat_id,
                self._chat_membership_status(chat) or "UNKNOWN",
                removed,
            )
            return

        portal = await Portal.get_by_chat_id(
            chat_id=chat_id,
            receiver=self.mxid,
            create=True,
            is_direct=False,
        )
        if portal is None:
            return
        title = getattr(chat, "title", None)
        if title and portal.name != title:
            portal.name = title
            await portal.save()
        await portal.ensure_matrix_user(
            self.mxid,
            reason="Обновление участия в MAX-группе или канале",
        )

    async def handle_max_reaction_update(self, event) -> None:
        """Передать обновление реакций MAX в соответствующий portal."""
        from .portal import Portal

        chat_id = getattr(event, "chat_id", None)
        if chat_id is None:
            log.debug("Игнорирую обновление реакций MAX без chat_id")
            return

        if await self._handle_blocked_chat_event(
            str(chat_id),
            event_kind="reaction_update",
        ):
            return

        try:
            chat_info = await self.max_client.get_chat_info(int(chat_id))
            is_direct = self._chat_is_direct(chat_info)
            if not is_direct and not self._chat_is_active_member(chat_info):
                await db_module.PortalUser.remove(str(chat_id), self.mxid)
                log.debug(
                    "Реакция из неактивного MAX-чата пропущена: "
                    "mxid=%s chat=%s status=%s",
                    self.mxid,
                    chat_id,
                    self._chat_membership_status(chat_info) or "UNKNOWN",
                )
                return
        except Exception:
            log.exception("Не удалось получить тип MAX-чата %s для реакции", chat_id)
            chat_info = None
            is_direct = True

        portal = await Portal.get_by_chat_id(
            chat_id=str(chat_id),
            receiver=self.mxid,
            create=False,
            is_direct=is_direct,
        )
        if portal is None or portal.mxid is None:
            log.debug(
                "Обновление реакций для MAX-чата %s пропущено: portal не создан",
                chat_id,
            )
            return

        if not is_direct:
            await portal.ensure_matrix_user(
                self.mxid,
                reason="Реакция из общей MAX-группы или канала",
            )
        await portal.handle_max_reaction_update(self, event, chat_info=chat_info)

    # --- Входящие сообщения из MAX ---

    async def handle_max_message(self, message) -> None:
        from .portal import Portal

        chat_id = getattr(message, "chat_id", None)
        if chat_id is None:
            log.debug("Игнорирую MAX-сообщение без chat_id")
            return

        if await self._handle_blocked_chat_event(
            str(chat_id),
            event_kind="message",
        ):
            return

        try:
            chat_info = await self.max_client.get_chat_info(int(chat_id))
            is_direct = self._chat_is_direct(chat_info)
            if not is_direct and not self._chat_is_active_member(chat_info):
                await db_module.PortalUser.remove(str(chat_id), self.mxid)
                log.info(
                    "Сообщение из неактивного MAX-чата пропущено без Matrix invite: "
                    "mxid=%s phone=%s chat=%s status=%s",
                    self.mxid,
                    self.max_phone,
                    chat_id,
                    self._chat_membership_status(chat_info) or "UNKNOWN",
                )
                return
        except Exception:
            log.exception("Не удалось получить тип MAX-чата %s", chat_id)
            chat_info = None
            is_direct = True

        portal = await Portal.get_by_chat_id(
            chat_id=str(chat_id),
            receiver=self.mxid,
            create=True,
            is_direct=is_direct,
        )
        if portal is None:
            log.warning("Не удалось создать portal для MAX-чата %s", chat_id)
            return

        if not is_direct:
            await portal.ensure_matrix_user(
                self.mxid,
                reason="Сообщение из общей MAX-группы или канала",
            )
        await portal.handle_max_message(self, message, chat_info=chat_info)
