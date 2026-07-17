from typing import Literal

from pymax.types import ContactInfo, Session, User

from .protocol import IClientProtocol


class UserMixin(IClientProtocol):
    def get_cached_user(self, user_id: int) -> User | None:
        """Возвращает пользователя из локального кеша без сетевого запроса.

        Args:
            user_id: ID пользователя.

        Returns:
            Контакт из кеша или ``None``, если клиент еще не знает такого
            пользователя.
        """
        return self._app.api.users.get_cached_user(user_id)

    async def get_users(self, user_ids: list[int]) -> list[User]:
        """Возвращает пользователей, беря известные контакты из кеша.

        Args:
            user_ids: ID пользователей в нужном порядке.

        Returns:
            Найденные контакты в порядке ``user_ids``. Недостающие контакты
            будут загружены с сервера и сохранены в кеш.
        """
        return await self._app.api.users.get_users(user_ids)

    async def get_user(self, user_id: int) -> User | None:
        """Возвращает пользователя из кеша или загружает его с сервера.

        Args:
            user_id: ID пользователя.

        Returns:
            Контакт или ``None``, если пользователь не найден.
        """
        return await self._app.api.users.get_user(user_id)

    async def fetch_users(self, user_ids: list[int]) -> list[User]:
        """Загружает пользователей с сервера и обновляет кеш клиента.

        Args:
            user_ids: ID пользователей.

        Returns:
            Контакты, которые вернул сервер.
        """
        return await self._app.api.users.fetch_users(user_ids)

    async def search_by_phone(self, phone: str) -> User:
        """Ищет пользователя Max по номеру телефона.

        Args:
            phone: Телефон в формате, который принимает Max. Обычно это
                международный формат с кодом страны.

        Returns:
            Найденный контакт. Результат сохраняется в кеш клиента.
        """
        return await self._app.api.users.search_by_phone(phone)

    async def get_sessions(self) -> list[Session]:
        """Возвращает активные сессии текущего аккаунта.

        Returns:
            Список сессий, известных серверу.
        """
        return await self._app.api.users.get_sessions()

    async def add_contact(self, contact_id: int) -> User:
        """Добавляет пользователя в контакты.

        Args:
            contact_id: ID пользователя.

        Returns:
            Обновленный контакт. Результат сохраняется в кеш клиента.
        """
        return await self._app.api.users.add_contact(contact_id)

    async def remove_contact(self, contact_id: int) -> Literal[True]:
        """Удаляет пользователя из контактов.

        Args:
            contact_id: ID пользователя.

        Returns:
            ``True``, если сервер принял запрос.
        """
        return await self._app.api.users.remove_contact(contact_id)

    async def import_contacts(self, contacts: list[ContactInfo]) -> list[User]:
        """Импортирует контакты из телефонной книги.

        Args:
            contacts: Контакты с телефоном и именем.

        Returns:
            Контакты Max, найденные или созданные сервером.
        """
        return await self._app.api.users.import_contacts(contacts)

    def get_chat_id(self, first_user_id: int, second_user_id: int) -> int:
        """Вычисляет ID личного чата для пары пользователей.

        Args:
            first_user_id: ID первого пользователя.
            second_user_id: ID второго пользователя.

        Returns:
            ID личного чата. Метод работает локально, без запроса к серверу.
        """
        return self._app.api.users.get_chat_id(first_user_id, second_user_id)
