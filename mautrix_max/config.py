from __future__ import annotations

from mautrix.bridge.config import BaseBridgeConfig
from mautrix.util.config import ConfigUpdateHelper


class Config(BaseBridgeConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        super().do_update(helper)
        copy = helper.copy

        copy("bridge.username_template")
        copy("bridge.displayname_template")
        copy("bridge.max.session_dir")
        copy("bridge.group_messages_via_bot")
        copy("bridge.media.max_size")
        copy("bridge.permissions")

        copy("max.device_type")
        copy("max.app_version")

    def get_permissions(self, mxid: str) -> tuple[str, bool, bool, bool]:
        """Разобрать bridge.permissions и вернуть права для данного mxid.

        Порядок приоритета: точный mxid > домен сервера > "*".
        Возвращает (level, relay_whitelisted, is_whitelisted, is_admin).
        """
        permissions: dict[str, str] = self["bridge.permissions"] or {}

        level = ""
        if mxid in permissions:
            level = permissions[mxid]
        else:
            homeserver = mxid.split(":", 1)[1] if ":" in mxid else ""
            if homeserver in permissions:
                level = permissions[homeserver]
            else:
                level = permissions.get("*", "")

        relay_whitelisted = level in ("relay", "user", "admin")
        is_whitelisted = level in ("user", "admin")
        is_admin = level == "admin"
        return level, relay_whitelisted, is_whitelisted, is_admin
