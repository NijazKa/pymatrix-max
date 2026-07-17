from __future__ import annotations

import logging
import re

from mautrix.bridge.commands import CommandEvent, HelpSection, command_handler
from pymax import PyMaxError

from . import db as db_module
from .portal import Portal
from .puppet import Puppet

log = logging.getLogger("mau.commands")

SECTION_AUTH = HelpSection("Authentication", 10, "")
SECTION_CONTACTS = HelpSection("Contacts", 20, "")
SECTION_CHATS = HelpSection("Chats", 30, "")

_PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_JOIN_URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_JOIN_TOKEN_RE = re.compile(r"(?:^|[\s<])(join/[^\s<>]+)", re.IGNORECASE)


def _normalize_phone(value: str) -> str | None:
    """Нормализовать международный номер, не меняя код страны."""
    phone = re.sub(r"[\s().-]+", "", value.strip())
    return phone if _PHONE_RE.fullmatch(phone) else None


def _normalize_join_link(value: str) -> str | None:
    """Извлечь MAX invite/public link из обычного или Matrix-formatted текста."""
    value = value.strip()
    if not value:
        return None

    url_match = _JOIN_URL_RE.search(value)
    if url_match:
        return url_match.group(0).rstrip(".,;!?)]}")

    token_match = _JOIN_TOKEN_RE.search(value)
    if token_match:
        return token_match.group(1).rstrip(".,;!?)]}")

    # PyMax also accepts a raw public channel identifier/link. Keep a single
    # whitespace-free token and let MAX validate its exact format.
    if not any(char.isspace() for char in value):
        return value.strip("<>[](){}'\"")
    return None


@command_handler(
    needs_auth=False,
    management_only=True,
    help_section=SECTION_AUTH,
    help_text="Начать вход в Max",
    help_args="<телефон в формате +79991234567>",
)
async def login(evt: CommandEvent) -> None:
    await evt.sender.remember_management_room(evt.room_id)
    if len(evt.args) < 1:
        await evt.reply("Использование: `login <телефон>`")
        return
    phone = evt.args[0]
    await evt.reply(
        "Начинаю авторизацию в Max. Дальнейшие запросы (код из SMS, "
        "при необходимости — пароль) придут отдельными сообщениями, "
        "просто отвечайте на них следующим сообщением без каких-либо команд."
    )
    await evt.sender.request_login_code(phone, evt.room_id)


@command_handler(
    needs_auth=False,
    management_only=True,
    help_section=SECTION_AUTH,
    help_text="Прервать текущий процесс входа в Max",
)
async def cancel(evt: CommandEvent) -> None:
    await evt.sender.remember_management_room(evt.room_id)
    if not evt.sender.command_status:
        await evt.reply("Сейчас нет активного процесса, который можно отменить")
        return
    await evt.sender.cancel_pending_login()
    await evt.reply("Вход в Max отменён")


@command_handler(
    needs_auth=True,
    management_only=True,
    help_section=SECTION_AUTH,
    help_text="Выйти из аккаунта Max",
)
async def logout(evt: CommandEvent) -> None:
    await evt.sender.remember_management_room(evt.room_id)
    await evt.sender.logout()
    await evt.reply("Вы вышли из Max")


@command_handler(
    needs_auth=False,
    management_only=True,
    help_text="Показать текущий стек выполнения фоновой задачи логина (для отладки)",
)
async def debug(evt: CommandEvent) -> None:
    await evt.sender.remember_management_room(evt.room_id)
    import asyncio

    all_tasks = asyncio.all_tasks()
    lines = [f"Всего задач в процессе: {len(all_tasks)}\n"]

    for task in all_tasks:
        name = task.get_name()
        coro = task.get_coro()
        coro_name = getattr(coro, "__qualname__", repr(coro))
        status = "done" if task.done() else "pending"
        line = f"• [{status}] {name} — {coro_name}"

        if task.done():
            try:
                exc = task.exception()
                if exc:
                    line += f"\n    EXCEPTION: {exc!r}"
            except Exception:
                pass
        else:
            stack = task.get_stack()
            if stack:
                top = stack[-1]
                line += f"\n    на {top.f_code.co_filename}:{top.f_lineno} in {top.f_code.co_name}"
            else:
                line += "\n    (стек пуст)"

        lines.append(line)

    text = "\n".join(lines)
    # Matrix-уведомление не резиновое, режем на части по 3000 символов
    for i in range(0, len(text), 3000):
        await evt.reply(f"```\n{text[i:i+3000]}\n```")


@command_handler(needs_auth=False, management_only=True, help_text="Проверить статус моста")
async def ping(evt: CommandEvent) -> None:
    await evt.sender.remember_management_room(evt.room_id)
    logged_in = await evt.sender.is_logged_in()
    await evt.reply(f"Мост работает. Вход в Max выполнен: {logged_in}")


@command_handler(
    needs_auth=True,
    management_only=True,
    help_section=SECTION_CONTACTS,
    help_text="Создать или открыть личный чат MAX по номеру телефона",
    help_args="<телефон в международном формате, например +79991234567>",
)
async def add(evt: CommandEvent) -> None:
    """Открыть существующий или создать новый Matrix portal для MAX DM."""
    await evt.sender.remember_management_room(evt.room_id)
    if not evt.args:
        await evt.reply("Использование: `add +79991234567`")
        return

    phone = _normalize_phone(" ".join(str(arg) for arg in evt.args))
    if phone is None:
        await evt.reply(
            "Некорректный номер. Используйте международный формат, "
            "например: `add +79991234567`"
        )
        return

    wrapper = evt.sender.max_client
    if wrapper is None or not wrapper.is_ready:
        await evt.reply("MAX-клиент ещё не готов. Проверьте вход командой `ping`.")
        return

    client = wrapper.client

    try:
        contact = await client.search_by_phone(phone)
        lookup_contact = contact
    except PyMaxError as exc:
        log.info(
            "MAX не нашёл пользователя по номеру для %s: %s",
            evt.sender.mxid,
            exc,
        )
        await evt.reply(
            "MAX не нашёл пользователя по этому номеру либо поиск по номеру "
            "запрещён настройками его аккаунта."
        )
        return
    except Exception:
        log.exception("Ошибка поиска MAX-пользователя по телефону")
        await evt.reply("Не удалось выполнить поиск пользователя в MAX.")
        return

    me = client.me
    own_contact = getattr(me, "contact", None)
    own_user_id = getattr(own_contact, "id", None)
    if own_user_id is None:
        own_user_id = getattr(me, "id", None)
    if own_user_id is None:
        log.error("PyMax не вернул ID текущего аккаунта для %s", evt.sender.mxid)
        await evt.reply("MAX не вернул ID текущего аккаунта. Перезапустите мост.")
        return

    remote_user_id = int(contact.id)
    if remote_user_id == int(own_user_id):
        await evt.reply("Это номер текущего MAX-аккаунта моста.")
        return

    # Добавление в адресную книгу полезно для нового диалога, но отказ сервера
    # не должен мешать открыть уже существующий чат или попробовать написать.
    try:
        contact = await client.add_contact(remote_user_id)
    except PyMaxError as exc:
        log.debug(
            "MAX не добавил контакт %s в адресную книгу, продолжаю открытие DM: %s",
            remote_user_id,
            exc,
        )
    except Exception:
        log.warning(
            "Ошибка добавления MAX-контакта %s; продолжаю открытие DM",
            remote_user_id,
            exc_info=True,
        )

    chat_id = int(client.get_chat_id(int(own_user_id), remote_user_id))

    try:
        puppet = await Puppet.get_by_max_id(str(remote_user_id))
        if puppet is None:
            raise RuntimeError("не удалось создать ghost-пользователя")
        await puppet.update_info(contact)
        if puppet.phone is None:
            # Успешный поиск по номеру подтверждает принадлежность номера этому
            # MAX-пользователю, даже если add_contact вернул сокращённый профиль.
            puppet.phone = Puppet.phone_from_info(lookup_contact) or phone
            await puppet.save()

        portal = await Portal.get_by_chat_id(
            chat_id=str(chat_id),
            receiver=evt.sender.mxid,
            create=True,
            is_direct=True,
        )
        if portal is None:
            raise RuntimeError("не удалось создать portal")

        room_created = portal.mxid is None
        portal.is_direct = True
        portal.remote_user_id = str(remote_user_id)
        portal.name = puppet.name or Puppet.display_name_from_info(contact) or phone
        await portal.save()

        if room_created:
            await portal.create_matrix_room(
                source=evt.sender,
                dm_puppet=puppet,
                chat_info=None,
            )
        else:
            await portal.sync_dm_contact_topic(puppet)

        if portal.mxid is None:
            raise RuntimeError("Matrix-комната не была создана")
    except Exception:
        log.exception(
            "Не удалось открыть MAX DM: mxid=%s user=%s chat=%s",
            evt.sender.mxid,
            remote_user_id,
            chat_id,
        )
        await evt.reply("Пользователь найден, но создать Matrix-чат не удалось.")
        return

    display_name = portal.name or phone
    action = "Создан новый чат" if room_created else "Чат уже был создан"
    room_link = f"https://matrix.to/#/{portal.mxid}"
    await evt.reply(f"{action}: [{display_name}]({room_link})")


async def _contact_max_id_from_event(evt: CommandEvent, portal: Portal | None) -> str | None:
    """Определить MAX ID контакта по DM, reply в группе или аргументу."""
    if portal is not None and portal.is_direct:
        return portal.remote_user_id

    try:
        reply_event_id = evt.content.get_reply_to()
    except AttributeError:
        reply_event_id = None

    if reply_event_id:
        # Relay-mode group messages are sent by the bridge bot, so the Matrix
        # sender no longer contains the MAX ID. Use message_map metadata first.
        mapped = await db_module.Message.get_by_mx_event(evt.room_id, reply_event_id)
        if mapped is not None and mapped.sender_max_id:
            return mapped.sender_max_id

        try:
            replied_event = await evt.main_intent.get_event(evt.room_id, reply_event_id)
        except Exception:
            log.warning(
                "Не удалось получить Matrix-событие для команды contact: room=%s event=%s",
                evt.room_id,
                reply_event_id,
                exc_info=True,
            )
        else:
            max_user_id = Puppet.get_id_from_mxid(replied_event.sender)
            if max_user_id:
                return max_user_id

    for arg in evt.args:
        value = str(arg).strip()
        if value.isdigit():
            return value

    return None


@command_handler(
    needs_auth=True,
    management_only=False,
    help_section=SECTION_CONTACTS,
    help_text="Показать имя, MAX ID и доступный телефон контакта",
    help_args="[MAX user ID; в группе можно ответить командой на сообщение]",
)
async def contact(evt: CommandEvent) -> None:
    portal = await Portal.get_by_mxid(evt.room_id)
    max_user_id = await _contact_max_id_from_event(evt, portal)
    if max_user_id is None:
        if portal is not None and not portal.is_direct:
            await evt.reply(
                "В группе ответьте командой `contact` на сообщение пользователя MAX "
                "либо укажите его MAX ID: `contact 123456789`."
            )
        else:
            await evt.reply(
                "Использование: `contact <MAX user ID>`. В личном MAX-чате аргумент не нужен."
            )
        return

    wrapper = evt.sender.max_client
    if wrapper is None or not wrapper.is_ready:
        await evt.reply("MAX-клиент не готов. Проверьте авторизацию командой `ping`.")
        return

    is_direct_contact = bool(
        portal is not None
        and portal.is_direct
        and portal.remote_user_id == max_user_id
    )

    # Read existing metadata directly from the bridge DB. This does not call
    # Puppet.get_by_max_id() and therefore cannot register a Synapse ghost for
    # a participant who only exists in a group.
    local_row = await db_module.Puppet.get_by_max_id(max_user_id)
    name = local_row.name if local_row is not None else None
    phone = local_row.phone if local_row is not None else None
    info = None

    try:
        info = await wrapper.get_user_info(int(max_user_id))
    except Exception as exc:
        log.info(
            "MAX не вернул свежий профиль контакта: requester=%s user=%s error=%s",
            evt.sender.mxid,
            max_user_id,
            exc,
        )
    else:
        name = Puppet.display_name_from_info(info) or name
        phone = Puppet.phone_from_info(info)

    # A real puppet is needed only for a direct chat, where it owns the Matrix
    # room and profile. Group-only contacts stay transient and are not written
    # to Synapse or the puppet table.
    if is_direct_contact:
        puppet = await Puppet.get_by_max_id(max_user_id)
        if puppet is None:
            await evt.reply("Не удалось открыть локальный профиль MAX-контакта.")
            return
        if info is not None:
            await puppet.update_info(info)
        name = puppet.name or name
        phone = puppet.phone
        await portal.sync_dm_contact_topic(puppet, clear_if_missing=True)

    if not name and info is None and local_row is None:
        await evt.reply("Не удалось получить профиль этого MAX-пользователя.")
        return

    display_name = name or f"MAX {max_user_id}"
    display_phone = f"`{phone}`" if phone else "не предоставлен MAX"
    await evt.reply(
        "Контакт MAX:\n"
        f"Имя: {display_name}\n"
        f"MAX ID: `{max_user_id}`\n"
        f"Телефон: {display_phone}"
    )


@command_handler(
    needs_auth=True,
    management_only=True,
    help_section=SECTION_CHATS,
    help_text="Вступить в MAX-группу или канал по ссылке",
    help_args="<invite-ссылка или публичная ссылка канала>",
)
async def join(evt: CommandEvent) -> None:
    """Join a MAX group/channel and create or open its Matrix portal."""
    await evt.sender.remember_management_room(evt.room_id)
    if not evt.args:
        await evt.reply(
            "Использование: `join https://max.ru/join/...` "
            "или `join <публичная ссылка канала>`"
        )
        return

    link = _normalize_join_link(" ".join(str(arg) for arg in evt.args))
    if link is None:
        await evt.reply("Не удалось распознать ссылку MAX. Пришлите её одним сообщением после `join`.")
        return

    wrapper = evt.sender.max_client
    if wrapper is None or not wrapper.is_ready:
        await evt.reply("MAX-клиент ещё не готов. Проверьте вход командой `ping`.")
        return

    # Resolve is optional, but useful for removing a previous local block
    # before CHAT_JOIN emits its chat-update push.
    preview = None
    preview_chat_id: str | None = None
    try:
        preview = await wrapper.resolve_chat_link(link)
    except ValueError:
        # Public channel links are valid for join_channel(), but not for the
        # group-only preview endpoint.
        pass
    except Exception as exc:
        log.debug(
            "Не удалось предварительно разрешить MAX-ссылку для %s: %s",
            evt.sender.mxid,
            exc,
        )

    if preview is not None and getattr(preview, "id", None) is not None:
        preview_chat_id = str(preview.id)
        # If the chat was previously blocked, its CHAT_UPDATE push must not
        # trigger auto-leave while this explicit join is in progress. The DB
        # denylist is removed only after MAX confirms the join.
        evt.sender.begin_explicit_chat_join(preview_chat_id)

    join_succeeded = False
    try:
        chat = await wrapper.join_chat_by_link(link)
        join_succeeded = True
    except ValueError:
        await evt.reply("MAX не распознал ссылку. Проверьте, что она скопирована полностью.")
        return
    except PyMaxError as exc:
        log.warning(
            "MAX отклонил вступление по ссылке: mxid=%s error=%s",
            evt.sender.mxid,
            exc,
        )
        await evt.reply(
            "MAX отклонил вступление. Ссылка могла истечь, вступление могло быть "
            "ограничено администраторами либо аккаунт уже не имеет доступа."
        )
        return
    except Exception:
        log.exception("Ошибка вступления в MAX-чат по ссылке для %s", evt.sender.mxid)
        await evt.reply("Не удалось вступить в MAX-чат. Подробности записаны в лог моста.")
        return
    finally:
        if not join_succeeded and preview_chat_id is not None:
            evt.sender.end_explicit_chat_join(preview_chat_id)

    chat_id_raw = getattr(chat, "id", None)
    if chat_id_raw is None:
        if preview_chat_id is not None:
            evt.sender.end_explicit_chat_join(preview_chat_id)
        log.error("MAX CHAT_JOIN не вернул chat.id для %s: %r", evt.sender.mxid, chat)
        await evt.reply("MAX подтвердил запрос, но не вернул ID чата.")
        return

    chat_id = str(chat_id_raw)
    if chat_id != preview_chat_id:
        evt.sender.begin_explicit_chat_join(chat_id)

    try:
        unblocked = await evt.sender.unblock_chat(chat_id)
    finally:
        evt.sender.end_explicit_chat_join(chat_id)
        if preview_chat_id is not None and preview_chat_id != chat_id:
            evt.sender.end_explicit_chat_join(preview_chat_id)

    chat_type = _chat_type_value(chat)
    if chat_type in {"DIALOG", "DIRECT", "DM"}:
        await evt.reply("Ссылка указывает на личный диалог, а не на группу или канал.")
        return

    try:
        portal = await Portal.get_by_chat_id(
            chat_id=chat_id,
            receiver=evt.sender.mxid,
            create=True,
            is_direct=False,
        )
        if portal is None:
            raise RuntimeError("не удалось создать portal")

        room_created = portal.mxid is None
        portal.is_direct = False
        portal.name = getattr(chat, "title", None) or portal.name or f"MAX {chat_id}"
        await portal.save()

        if room_created:
            await portal.create_matrix_room(source=evt.sender, chat_info=chat)
        else:
            await portal.ensure_matrix_user(
                evt.sender.mxid,
                reason="Вступление в MAX-чат по ссылке",
            )

        if portal.mxid is None:
            raise RuntimeError("Matrix-комната не была создана")
    except Exception:
        log.exception(
            "В MAX-чат вступили, но Matrix portal создать/открыть не удалось: "
            "mxid=%s chat=%s",
            evt.sender.mxid,
            chat_id,
        )
        await evt.reply(
            f"В MAX-чат `{chat_id}` вступили, но открыть Matrix-комнату не удалось. "
            "Следующее обычное сообщение из чата должно повторить создание portal."
        )
        return

    kind = "канал" if chat_type == "CHANNEL" else "чат"
    action = "Создана Matrix-комната" if room_created else "Открыта существующая Matrix-комната"
    room_link = f"https://matrix.to/#/{portal.mxid}"
    suffix = " Локальная блокировка этого чата снята." if unblocked else ""
    await evt.reply(
        f"Вступление в MAX-{kind} выполнено. {action}: "
        f"[{portal.name or chat_id}]({room_link}).{suffix}"
    )


@command_handler(
    needs_auth=True,
    management_only=True,
    help_section=SECTION_CHATS,
    help_text="Проверить приглашения в общие MAX-группы и каналы",
    help_args="[chat_id или Matrix room_id]",
)
async def syncgroups(evt: CommandEvent) -> None:
    """Reconcile shared portals from the chat list or one exact chat ID."""
    await evt.sender.remember_management_room(evt.room_id)
    wrapper = evt.sender.max_client
    if wrapper is None or not wrapper.is_ready:
        await evt.reply("MAX-клиент не готов. Проверьте авторизацию командой `ping`.")
        return

    target = " ".join(str(arg) for arg in evt.args).strip()
    if target:
        chat_id = target
        if target.startswith("!"):
            portal = await Portal.get_by_mxid(target)
            if portal is None:
                await evt.reply(f"Matrix-комната `{target}` не связана с MAX portal.")
                return
            chat_id = str(portal.chat_id)

        try:
            result = await evt.sender.sync_group_portal_by_chat_id(chat_id)
        except Exception as exc:
            log.exception(
                "Не удалось точно синхронизировать общий MAX portal: mxid=%s target=%r",
                evt.sender.mxid,
                target,
            )
            await evt.reply(
                "Точная синхронизация не выполнена: "
                f"`{type(exc).__name__}: {exc}`"
            )
            return

        if result["blocked"]:
            await evt.reply(
                f"MAX-чат `{result['chat_id']}` находится в локальном denylist. "
                "Сначала выполните `unblock <chat_id>`."
            )
            return

        if result.get("active") is False:
            await evt.reply(
                f"MAX подтверждает, что аккаунт больше не состоит в чате "
                f"`{result['chat_id']}` (status={result.get('status') or 'UNKNOWN'}). "
                "Устаревшая связь `portal_user` удалена; повторного приглашения "
                "в Matrix-комнату не будет. Саму Matrix-комнату можно покинуть "
                "обычной кнопкой Element."
            )
            return

        room_id = result["room_id"]
        room_link = f"https://matrix.to/#/{room_id}" if room_id else None
        action = "создана" if result["created"] else "найдена"
        if room_link:
            await evt.reply(
                f"Группа/канал подтверждены через MAX API. Matrix-комната {action}: "
                f"[{result['name'] or result['chat_id']}]({room_link}). "
                "Связь пользователя записана в `portal_user`, приглашение проверено."
            )
        else:
            await evt.reply(
                f"Группа/канал `{result['chat_id']}` подтверждены, "
                "но Matrix-комната не определена."
            )
        return

    try:
        stats = await evt.sender.sync_group_portals(refresh=True)
    except Exception:
        log.exception("Не удалось синхронизировать общие MAX portal для %s", evt.sender.mxid)
        await evt.reply("Синхронизация групп и каналов завершилась с ошибкой. Подробности в логе.")
        return

    await evt.reply(
        "Синхронизация завершена: "
        f"MAX-групп/каналов в текущей странице списка — {stats['known']}, "
        f"существующих Matrix portal — {stats['portals']}, "
        f"проверено приглашений — {stats['associated']}, "
        f"заблокировано — {stats['blocked']}, "
        f"неактивных связей удалено — {stats.get('inactive', 0)}. "
        "Для старого тихого чата используйте `syncgroups <chat_id>`."
    )


async def _resolve_chat_target(evt: CommandEvent) -> tuple[Portal | None, str | None, str | None]:
    """Resolve a MAX chat from the current portal room or an explicit ID."""
    portal = await Portal.get_by_mxid(evt.room_id)
    if portal is not None:
        return portal, str(portal.chat_id), portal.name

    for arg in evt.args:
        value = str(arg).strip()
        if value.startswith("--"):
            continue
        try:
            int(value)
        except ValueError:
            continue
        return None, value, None

    return None, None, None


def _chat_type_value(chat_info) -> str:
    chat_type = getattr(chat_info, "type", None)
    return str(getattr(chat_type, "value", chat_type) or "").upper()


def _chat_status_value(chat_info) -> str:
    status = getattr(chat_info, "status", None)
    return str(getattr(status, "value", status) or "").strip().upper()


def _chat_is_active_member(chat_info) -> bool:
    status = _chat_status_value(chat_info)
    return not status or status == "ACTIVE"


def _is_already_left_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "chat.exit.not.active.user" in text
        or "not active chat member" in text
        or "not active member" in text
    )


async def _leave_remote_chat(evt: CommandEvent, *, block: bool) -> None:
    portal, chat_id, known_name = await _resolve_chat_target(evt)
    if chat_id is None:
        command = "block" if block else "leave"
        await evt.reply(
            f"Использование в комнате MAX-группы: `{command}`. "
            f"Из management-комнаты: `{command} <chat_id>`."
        )
        return

    if portal is not None and portal.is_direct:
        await evt.reply("Из личного диалога выйти нельзя. Команда поддерживает группы и каналы.")
        return

    wrapper = evt.sender.max_client
    if wrapper is None or not wrapper.is_ready:
        await evt.reply("MAX-клиент не готов. Проверьте авторизацию командой `ping`.")
        return

    chat_info = None
    display_name = known_name or chat_id
    try:
        chat_info = await wrapper.get_chat_info(int(chat_id))
        type_value = _chat_type_value(chat_info)
        if type_value in {"DIALOG", "DIRECT", "DM"}:
            await evt.reply("Из личного диалога выйти нельзя. Команда поддерживает группы и каналы.")
            return
        display_name = getattr(chat_info, "title", None) or display_name

        if not _chat_is_active_member(chat_info):
            if block:
                await evt.sender.block_chat(chat_id, display_name)
            await db_module.PortalUser.remove(chat_id, evt.sender.mxid)
            await evt.reply(
                f"MAX подтверждает, что вы уже не состоите в чате «{display_name}» "
                f"(status={_chat_status_value(chat_info) or 'UNKNOWN'}). "
                "Устаревшая связь с Matrix-порталом удалена. "
                + (
                    "Чат также добавлен в denylist. "
                    if block
                    else "Повторное приглашение мост больше не создаст. "
                )
                + "Matrix-комнату можно покинуть обычной кнопкой Element."
            )
            return
    except Exception as exc:
        if not block:
            log.warning(
                "Не удалось получить MAX-чат перед выходом: mxid=%s chat=%s error=%s",
                evt.sender.mxid,
                chat_id,
                exc,
            )
            await evt.reply("Не удалось получить сведения о MAX-чате. Выход не выполнен.")
            return
        log.warning(
            "Не удалось получить заблокированный MAX-чат %s для %s; "
            "сохраняю denylist и попробую выйти при следующем push-событии: %s",
            chat_id,
            evt.sender.mxid,
            exc,
        )

    if block:
        await evt.sender.block_chat(chat_id, display_name)
        # The leave operation itself may emit a chat-update push. Mark this
        # attempt before calling MAX so the callback doesn't send a duplicate
        # leave request. If the request fails, the throttle is cleared.
        evt.sender.mark_blocked_leave_attempt(chat_id)

    try:
        await wrapper.leave_chat(int(chat_id), chat_info=chat_info)
    except Exception as exc:
        if _is_already_left_error(exc):
            if block:
                # The denylist entry created above remains intentionally active.
                evt.sender.clear_blocked_leave_attempt(chat_id)
            removed = await db_module.PortalUser.remove(chat_id, evt.sender.mxid)
            log.info(
                "MAX-чат уже покинут; stale Matrix association cleaned: "
                "mxid=%s chat=%s block=%s removed=%s error=%s",
                evt.sender.mxid,
                chat_id,
                block,
                removed,
                exc,
            )
            await evt.reply(
                f"MAX подтверждает, что вы уже не состоите в чате «{display_name}». "
                "Устаревшая связь с Matrix-порталом удалена. "
                + (
                    "Чат остаётся в denylist. "
                    if block
                    else "Повторного приглашения после синхронизации не будет. "
                )
                + "Matrix-комнату можно покинуть обычной кнопкой Element."
            )
            return

        if block:
            evt.sender.clear_blocked_leave_attempt(chat_id)
            log.warning(
                "Чат %s добавлен в denylist для %s, но немедленный выход не удался: %s",
                chat_id,
                evt.sender.mxid,
                exc,
            )
            await evt.reply(
                f"Чат «{display_name}» заблокирован мостом, но немедленно выйти из MAX "
                "не удалось. При следующем событии мост повторит выход автоматически."
            )
            return

        log.exception(
            "Не удалось выйти из MAX-чата: mxid=%s chat=%s",
            evt.sender.mxid,
            chat_id,
        )
        await evt.reply("MAX отклонил выход из чата. Подробности записаны в лог.")
        return

    await db_module.PortalUser.remove(chat_id, evt.sender.mxid)

    if block:
        await evt.reply(
            f"Вы вышли из MAX-чата «{display_name}», и он добавлен в denylist. "
            "Если аккаунт снова добавят, мост автоматически выйдет при первом push-событии "
            "и не будет пробрасывать чат в Element. Matrix-комнату можно покинуть обычной "
            "кнопкой Element."
        )
    else:
        await evt.reply(
            f"Вы вышли из MAX-чата «{display_name}». Matrix-комнату мост не может "
            "покинуть от имени вашего Matrix-аккаунта, поэтому её можно закрыть обычной "
            "кнопкой Element."
        )


@command_handler(
    needs_auth=True,
    management_only=False,
    help_section=SECTION_CHATS,
    help_text="Выйти из текущей MAX-группы или канала",
    help_args="[chat_id — только для management-комнаты]",
)
async def leave(evt: CommandEvent) -> None:
    await _leave_remote_chat(evt, block=False)


@command_handler(
    needs_auth=True,
    management_only=False,
    help_section=SECTION_CHATS,
    help_text="Выйти из MAX-чата и автоматически выходить при повторном добавлении",
    help_args="[chat_id — только для management-комнаты]",
)
async def block(evt: CommandEvent) -> None:
    await _leave_remote_chat(evt, block=True)


@command_handler(
    needs_auth=False,
    management_only=False,
    help_section=SECTION_CHATS,
    help_text="Снять локальную блокировку MAX-чата",
    help_args="[chat_id — только для management-комнаты]",
)
async def unblock(evt: CommandEvent) -> None:
    _portal, chat_id, name = await _resolve_chat_target(evt)
    if chat_id is None:
        await evt.reply(
            "Использование в комнате заблокированного чата: `unblock`. "
            "Из management-комнаты: `unblock <chat_id>`."
        )
        return

    removed = await evt.sender.unblock_chat(chat_id)
    if removed:
        await evt.reply(f"Локальная блокировка MAX-чата «{name or chat_id}» снята.")
    else:
        await evt.reply(f"MAX-чат `{chat_id}` не был заблокирован для этого аккаунта.")


@command_handler(
    needs_auth=False,
    management_only=True,
    help_section=SECTION_CHATS,
    help_text="Показать локально заблокированные MAX-чаты",
)
async def blocked(evt: CommandEvent) -> None:
    await evt.sender.remember_management_room(evt.room_id)
    rows = await evt.sender.get_blocked_chats()
    if not rows:
        await evt.reply("Локально заблокированных MAX-чатов нет.")
        return

    lines = ["Заблокированные MAX-чаты:"]
    for item in rows:
        label = item.name or "без названия"
        lines.append(f"• `{item.chat_id}` — {label}")
    lines.append("\nСнять блокировку: `unblock <chat_id>`")
    await evt.reply("\n".join(lines))
