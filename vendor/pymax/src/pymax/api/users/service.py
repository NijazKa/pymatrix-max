from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pymax.api.binding import bind_api_model
from pymax.api.response import (
    parse_payload_list,
    require_payload_dict,
    require_payload_item_model,
)
from pymax.logging import get_logger
from pymax.protocol import InboundFrame, Opcode
from pymax.types.domain import ContactInfo, Session, User

from .enums import ContactAction, UserPayloadKey
from .payloads import (
    ContactActionPayload,
    FetchContactsPayload,
    ImportContactsPayload,
    SearchByPhonePayload,
)

if TYPE_CHECKING:
    from pymax.app import App


logger = get_logger(__name__)


class UserService:
    def __init__(self, app: App) -> None:
        self.app = app

    def _cache_user(self, user: User) -> User:
        user = bind_api_model(self.app, user)
        self.app.users[user.id] = user
        return user

    def get_cached_user(self, user_id: int) -> User | None:
        user = self.app.users.get(user_id)
        logger.debug("get_cached_user id=%s hit=%s", user_id, bool(user))
        return bind_api_model(self.app, user) if user is not None else None

    async def get_users(self, user_ids: list[int]) -> list[User]:
        cached = {
            user_id: user
            for user_id in user_ids
            if (user := self.get_cached_user(user_id)) is not None
        }
        missing_ids = [user_id for user_id in user_ids if user_id not in cached]

        if missing_ids:
            for user in await self.fetch_users(missing_ids):
                cached[user.id] = user

        return [cached[user_id] for user_id in user_ids if user_id in cached]

    async def get_user(self, user_id: int) -> User | None:
        if user := self.get_cached_user(user_id):
            return user

        users = await self.fetch_users([user_id])
        return users[0] if users else None

    async def fetch_users(self, user_ids: list[int]) -> list[User]:
        logger.info("fetching users count=%s", len(user_ids))
        frame = FetchContactsPayload(contact_ids=user_ids)
        response = await self.app.invoke(Opcode.CONTACT_INFO, frame.to_payload())

        users = [
            self._cache_user(user)
            for user in parse_payload_list(response, UserPayloadKey.CONTACTS, User)
        ]
        logger.debug("fetched users count=%s", len(users))
        return users

    async def search_by_phone(self, phone: str) -> User:
        logger.info("searching user by phone phone_set=%s", bool(phone))
        frame = SearchByPhonePayload(phone=phone)
        response = await self.app.invoke(
            Opcode.CONTACT_INFO_BY_PHONE,
            frame.to_payload(),
        )

        contact = require_payload_item_model(
            response,
            UserPayloadKey.CONTACT,
            User,
        )
        return self._cache_user(contact)

    async def get_sessions(self) -> list[Session]:
        logger.info("fetching sessions")
        response = await self.app.invoke(Opcode.SESSIONS_INFO, {})
        return parse_payload_list(response, UserPayloadKey.SESSIONS, Session)

    async def _contact_action(self, payload: ContactActionPayload) -> InboundFrame:
        response = await self.app.invoke(Opcode.CONTACT_UPDATE, payload.to_payload())
        require_payload_dict(response)
        return response

    async def add_contact(self, contact_id: int) -> User:
        response = await self._contact_action(
            ContactActionPayload(
                contact_id=contact_id,
                action=ContactAction.ADD,
            )
        )
        contact = require_payload_item_model(
            response,
            UserPayloadKey.CONTACT,
            User,
        )
        return self._cache_user(contact)

    async def remove_contact(self, contact_id: int) -> Literal[True]:
        await self._contact_action(
            ContactActionPayload(
                contact_id=contact_id,
                action=ContactAction.REMOVE,
            )
        )
        self.app.users.pop(contact_id, None)
        return True

    async def import_contacts(self, contacts: list[ContactInfo]) -> list[User]:
        frame = ImportContactsPayload.from_contacts(contacts)

        response = await self.app.invoke(Opcode.SYNC, frame.to_payload())

        users = parse_payload_list(
            response, UserPayloadKey.CONTACTS, User
        )  # TODO: maybe also return phone mapping?

        # {contacts: [...], phones: {data[0]: server_phone}}
        return [self._cache_user(user) for user in users]

    def get_chat_id(self, first_user_id: int, second_user_id: int) -> int:
        return first_user_id ^ second_user_id
