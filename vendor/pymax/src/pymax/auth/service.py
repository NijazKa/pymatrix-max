from __future__ import annotations

from typing import TYPE_CHECKING

from pymax.logging import get_logger

from .providers import SmsCodeProvider
from .sms import SmsAuthFlow

if TYPE_CHECKING:
    from pymax.app import App


logger = get_logger(__name__)


class AuthService:
    def __init__(self, app: App, sms_code_provider: SmsCodeProvider) -> None:
        self.app = app
        self.sms_code_provider = sms_code_provider
        self.sms = SmsAuthFlow(self.sms_code_provider)
        logger.debug(
            "auth service initialized sms_provider=%s",
            type(sms_code_provider).__name__,
        )
