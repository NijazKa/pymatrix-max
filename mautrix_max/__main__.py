from __future__ import annotations

from mautrix.bridge import Bridge
from mautrix.types import RoomID, UserID

from . import commands  # noqa: F401
from . import db as db_module
from .config import Config
from .db.upgrade import upgrade_table
from .matrix import MatrixHandler
from .portal import Portal
from .puppet import Puppet
from .user import User


class MaxBridge(Bridge):
    name = "mautrix-max"
    module = "mautrix_max"
    command = "python -m mautrix_max"
    description = "Неофициальный мост Matrix ↔ MAX через PyMax."
    repo_url = "https://github.com/NijazKa/pymatrix-max"
    version = "0.12.0"
    config_class = Config
    matrix_class = MatrixHandler
    upgrade_table = upgrade_table

    def prepare_config(self) -> None:
        super().prepare_config()
        User.config = self.config

    def prepare_bridge(self) -> None:
        super().prepare_bridge()
        User.az = self.az
        User.bridge = self
        User.loop = self.loop

        Portal.az = self.az
        Portal.bridge = self
        Portal.matrix = self.matrix
        Portal.loop = self.loop

        Puppet.az = self.az
        Puppet.mx = self.matrix
        Puppet.loop = self.loop

    def prepare_db(self) -> None:
        super().prepare_db()
        db_module.init(self.db)

    async def get_user(self, user_id: UserID, create: bool = True):
        return await User.get_by_mxid(user_id, create=create)

    async def get_portal(self, room_id: RoomID):
        return await Portal.get_by_mxid(room_id)

    async def get_puppet(self, user_id: UserID, create: bool = False):
        max_id = Puppet.get_id_from_mxid(user_id)
        if not max_id:
            return None
        return await Puppet.get_by_max_id(max_id, create=create)

    async def get_double_puppet(self, user_id: UserID):
        return await Puppet.get_by_custom_mxid(user_id)

    def is_bridge_ghost(self, user_id: UserID) -> bool:
        return Puppet.get_id_from_mxid(user_id) is not None

    async def count_logged_in_users(self) -> int:
        return len(
            [
                user
                for user in User.by_mxid.values()
                if user.max_client is not None and user.max_client.is_ready
            ]
        )

    async def start(self) -> None:
        await super().start()
        users = await User.all_logged_in()
        self.log.info("Восстанавливаю PyMax-клиенты для %d пользователей", len(users))
        for user in users:
            try:
                await user.start_max_client()
            except Exception:
                self.log.exception("Не удалось восстановить PyMax-клиент для %s", user.mxid)


def main() -> None:
    MaxBridge().run()


if __name__ == "__main__":
    main()
