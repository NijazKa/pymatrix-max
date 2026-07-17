from .auth import AuthMixin
from .bots import BotsMixin
from .chat import ChatMixin
from .message import MessageMixin
from .self import SelfMixin
from .user import UserMixin


class BaseMixin(
    SelfMixin,
    UserMixin,
    ChatMixin,
    MessageMixin,
    BotsMixin,
    AuthMixin,
):
    """Собирает публичные API-методы клиента."""
