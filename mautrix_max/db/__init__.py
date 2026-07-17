from mautrix.util.async_db import Database

from .blocked_chat import BlockedChat
from .message import Message
from .portal import Portal
from .portal_user import PortalUser
from .reaction import Reaction
from .puppet import Puppet
from .upgrade import upgrade_table
from .user import User


def init(db: Database) -> None:
    for table in (Portal, Puppet, User, Message, Reaction, BlockedChat, PortalUser):
        table.db = db


__all__ = [
    "upgrade_table",
    "init",
    "Portal",
    "Puppet",
    "User",
    "Message",
    "Reaction",
    "BlockedChat",
    "PortalUser",
]
