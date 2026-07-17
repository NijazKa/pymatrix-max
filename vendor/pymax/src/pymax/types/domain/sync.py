from pydantic import BaseModel

DEFAULT_CONFIG_HASH = (
    "00000000-0000000000000000-00000000-"
    "0000000000000000-0000000000000000-0-"
    "0000000000000000-00000000"
)

ConfigHash = str | int


class SyncState(BaseModel):
    """Полное сохраненное состояние синхронизации Max.

    Обычно PyMax управляет этим объектом сам и хранит его в файле сессии.
    Пользователю чаще нужен ``SyncOverrides`` для временного сброса одного или
    нескольких маркеров.

    Args:
        chats_sync: Маркер sync для списка чатов.
        contacts_sync: Маркер sync для контактов.
        drafts_sync: Маркер sync для черновиков.
        presence_sync: Маркер sync для presence.
        config_hash: Хеш конфигурации Max.

    Example:
        .. code-block:: python

           from pymax import SyncState

           state = SyncState(chats_sync=-1)
    """

    chats_sync: int = -1
    contacts_sync: int = -1
    drafts_sync: int = -1
    presence_sync: int = -1
    config_hash: ConfigHash = DEFAULT_CONFIG_HASH


class SyncOverrides(BaseModel):
    """Частичные переопределения состояния синхронизации.

    :ivar chats_sync: Новая метка синхронизации чатов.
    :vartype chats_sync: int | None
    :ivar contacts_sync: Новая метка синхронизации контактов.
    :vartype contacts_sync: int | None
    :ivar drafts_sync: Новая метка синхронизации черновиков.
    :vartype drafts_sync: int | None
    :ivar presence_sync: Новая метка синхронизации присутствия.
    :vartype presence_sync: int | None
    :ivar config_hash: Новый хеш конфигурации.
    :vartype config_hash: ConfigHash | None
    """

    chats_sync: int | None = None
    contacts_sync: int | None = None
    drafts_sync: int | None = None
    presence_sync: int | None = None
    config_hash: ConfigHash | None = None

    def resolve(self, saved: SyncState) -> SyncState:
        """Собирает полное состояние из переопределений и сохраненных данных.

        :param saved: Сохраненное состояние синхронизации.
        :type saved: SyncState
        :returns: Полное состояние синхронизации.
        :rtype: SyncState
        """
        return SyncState(
            chats_sync=(self.chats_sync if self.chats_sync is not None else saved.chats_sync),
            contacts_sync=(
                self.contacts_sync if self.contacts_sync is not None else saved.contacts_sync
            ),
            drafts_sync=(self.drafts_sync if self.drafts_sync is not None else saved.drafts_sync),
            presence_sync=(
                self.presence_sync if self.presence_sync is not None else saved.presence_sync
            ),
            config_hash=(self.config_hash if self.config_hash is not None else saved.config_hash),
        )
