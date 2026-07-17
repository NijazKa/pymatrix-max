from __future__ import annotations

from mautrix.bridge import BaseMatrixHandler
from mautrix.types import ReactionEvent, RedactionEvent, RelationType

from . import db as db_module
from .portal import Portal
from .puppet import Puppet
from .user import User


class MatrixHandler(BaseMatrixHandler):
    async def get_portal(self, room_id):
        return await Portal.get_by_mxid(room_id)

    async def get_puppet(self, user_id, create: bool = False):
        max_id = Puppet.get_id_from_mxid(user_id)
        if not max_id:
            return None
        return await Puppet.get_by_max_id(max_id, create=create)

    async def get_user(self, user_id, create: bool = True):
        return await User.get_by_mxid(user_id, create=create)

    @staticmethod
    async def allow_bridging_message(user: "User", portal: "Portal") -> bool:
        if not await user.is_logged_in():
            return False
        if await db_module.BlockedChat.is_blocked(user.mxid, str(portal.chat_id)):
            return False
        if (
            not portal.is_direct
            and not await db_module.PortalUser.exists(str(portal.chat_id), user.mxid)
        ):
            return False
        return True

    async def _get_reaction_context(self, evt):
        portal = await Portal.get_by_mxid(evt.room_id)
        if portal is None:
            self.log.debug(
                "Игнорирую %s в комнате без MAX portal: %s",
                evt.type,
                evt.room_id,
            )
            return None, None

        user = await User.get_by_mxid(evt.sender, create=True)
        if user is None or not user.is_whitelisted:
            self.log.debug("Пользователь %s не может использовать реакции", evt.sender)
            return None, None

        if not await self.allow_bridging_message(user, portal):
            self.log.debug("Пользователь %s не авторизован в MAX", evt.sender)
            return None, None

        return portal, user

    async def handle_event(self, evt) -> None:
        if isinstance(evt, ReactionEvent):
            relates_to = evt.content.relates_to
            if (
                relates_to.rel_type != RelationType.ANNOTATION
                or not relates_to.event_id
                or not relates_to.key
            ):
                self.log.debug("Игнорирую некорректную Matrix-реакцию %s", evt.event_id)
                return

            portal, user = await self._get_reaction_context(evt)
            if portal is None or user is None:
                return

            await portal.handle_matrix_reaction(
                sender=user,
                target_event_id=relates_to.event_id,
                reaction=str(relates_to.key),
                reaction_event_id=evt.event_id,
            )
            return

        if isinstance(evt, RedactionEvent):
            portal, user = await self._get_reaction_context(evt)
            if portal is None or user is None:
                return

            handled = await portal.handle_matrix_reaction_redaction(
                sender=user,
                redacted_event_id=evt.redacts,
                redaction_event_id=evt.event_id,
            )
            if handled:
                return

        await super().handle_event(evt)
