from __future__ import annotations

import re

from mautrix.bridge import BasePuppet
from mautrix.types import UserID

from . import db as db_module

USERNAME_TEMPLATE = "max_{userid}"
_username_regex = re.compile(
    "^" + re.escape(USERNAME_TEMPLATE).replace(r"\{userid\}", r"(.+)") + "$"
)


class Puppet(BasePuppet):
    by_max_id: dict[str, "Puppet"] = {}
    by_custom_mxid: dict[UserID, "Puppet"] = {}

    max_user_id: str
    name: str | None
    phone: str | None
    avatar_url: str | None
    custom_mxid: UserID | None
    _db_row: db_module.Puppet | None = None

    def __init__(self, max_user_id: str) -> None:
        self.max_user_id = max_user_id
        self.is_registered = False

        self.default_mxid = self.get_mxid_from_id(max_user_id)
        self.default_mxid_intent = self.az.intent.user(self.default_mxid)
        self.custom_mxid = None
        self.access_token = None
        self.base_url = None
        self.intent = self.default_mxid_intent
        self.name = None
        self.phone = None
        self.avatar_url = None
        super().__init__()

    @classmethod
    def get_mxid_from_id(cls, max_user_id: str) -> UserID:
        localpart = USERNAME_TEMPLATE.format(userid=max_user_id)
        return UserID(f"@{localpart}:{cls.az.domain}")

    @classmethod
    def get_id_from_mxid(cls, mxid: UserID) -> str | None:
        try:
            localpart = mxid[1 : mxid.index(":")]
        except ValueError:
            return None
        match = _username_regex.match(localpart)
        return match.group(1) if match else None

    @classmethod
    async def get_by_mxid(cls, mxid: UserID) -> "Puppet | None":
        max_user_id = cls.get_id_from_mxid(mxid)
        if not max_user_id:
            return None
        return await cls.get_by_max_id(max_user_id, create=False)

    @classmethod
    async def get_by_max_id(cls, max_user_id: str, create: bool = True) -> "Puppet | None":
        if max_user_id in cls.by_max_id:
            return cls.by_max_id[max_user_id]

        row = await db_module.Puppet.get_by_max_id(max_user_id)
        puppet = cls(max_user_id)
        if row:
            puppet._db_row = row
            puppet.name = row.name
            puppet.phone = row.phone
            puppet.avatar_url = row.avatar_url
            puppet.custom_mxid = row.custom_mxid
            puppet.intent = puppet.default_mxid_intent
        elif create:
            puppet._db_row = db_module.Puppet(
                db=db_module.Puppet.db,
                max_user_id=max_user_id,
                mxid=puppet.default_mxid,
                name=None,
                phone=None,
                avatar_url=None,
                custom_mxid=None,
            )
            await puppet._db_row.insert()
        else:
            return None

        # Кэшируем ДО ensure_registered(). State store mautrix во время
        # проверки регистрации вызывает bridge.get_puppet(), который снова
        # попадает сюда. Без раннего кэширования возникает бесконечная рекурсия.
        cls.by_max_id[max_user_id] = puppet
        if puppet.custom_mxid:
            cls.by_custom_mxid[puppet.custom_mxid] = puppet

        try:
            await puppet.intent.ensure_registered()
        except Exception:
            # Не оставляем в кэше частично инициализированный объект: следующая
            # попытка сможет создать/зарегистрировать puppet заново.
            cls.by_max_id.pop(max_user_id, None)
            if puppet.custom_mxid:
                cls.by_custom_mxid.pop(puppet.custom_mxid, None)
            raise

        return puppet

    @classmethod
    async def get_by_custom_mxid(cls, mxid: UserID) -> "Puppet | None":
        if mxid in cls.by_custom_mxid:
            return cls.by_custom_mxid[mxid]
        row = await db_module.Puppet.get_by_custom_mxid(mxid)
        if not row:
            return None
        puppet = cls(row.max_user_id)
        puppet._db_row = row
        puppet.name = row.name
        puppet.phone = row.phone
        puppet.avatar_url = row.avatar_url
        puppet.custom_mxid = row.custom_mxid
        puppet.intent = puppet.default_mxid_intent

        # Аналогично get_by_max_id(): state store должен увидеть уже
        # закэшированный puppet во время ensure_registered().
        cls.by_custom_mxid[mxid] = puppet
        cls.by_max_id[row.max_user_id] = puppet

        try:
            await puppet.intent.ensure_registered()
        except Exception:
            cls.by_custom_mxid.pop(mxid, None)
            cls.by_max_id.pop(row.max_user_id, None)
            raise

        return puppet

    async def save(self) -> None:
        if not self._db_row:
            return
        self._db_row.name = self.name
        self._db_row.phone = self.phone
        self._db_row.avatar_url = self.avatar_url
        self._db_row.custom_mxid = self.custom_mxid
        await self._db_row.save()

    @staticmethod
    def display_name_from_info(info) -> str | None:
        if info is None:
            return None
        direct_name = getattr(info, "name", None)
        if direct_name:
            return str(direct_name).strip() or None

        for item in getattr(info, "names", None) or []:
            full = getattr(item, "name", None)
            if full and str(full).strip():
                return str(full).strip()
            first = str(getattr(item, "first_name", None) or "").strip()
            last = str(getattr(item, "last_name", None) or "").strip()
            combined = " ".join(part for part in (first, last) if part)
            if combined:
                return combined
        return None

    @staticmethod
    def phone_from_info(info) -> str | None:
        """Нормализовать телефон, если MAX вернул его в профиле контакта."""
        if info is None:
            return None
        raw_phone = (
            info.get("phone") if isinstance(info, dict) else getattr(info, "phone", None)
        )
        if raw_phone is None:
            return None

        digits = re.sub(r"\D+", "", str(raw_phone))
        if not digits:
            return None
        return f"+{digits}"

    async def update_info(self, info) -> set[str]:
        """Синхронизировать имя и доступный телефон ghost-пользователя из MAX."""
        changed: set[str] = set()
        display_name = self.display_name_from_info(info)
        phone = self.phone_from_info(info)

        if display_name and display_name != self.name:
            self.name = display_name
            changed.add("name")

        # Если MAX перестал возвращать номер, удаляем ранее сохранённое значение.
        if phone != self.phone:
            self.phone = phone
            changed.add("phone")

        if not changed:
            return changed

        if "name" in changed and self.name:
            await self.intent.ensure_registered()
            await self.intent.set_displayname(self.name)
        await self.save()
        return changed
