from pydantic import BaseModel, Field

from pymax.api.auth.enums import AuthType
from pymax.api.models import CamelModel

from .profile import Profile


class StartAuthResponse(CamelModel):
    """Ответ на начало авторизации.

    :ivar token: Токен авторизационного запроса.
    :vartype token: str
    :ivar code_length: Длина кода подтверждения.
    :vartype code_length: int
    :ivar request_max_duration: Максимальное время ожидания запроса кода.
    :vartype request_max_duration: int
    :ivar request_count_left: Количество оставшихся запросов кода.
    :vartype request_count_left: int
    :ivar alt_action_duration: Время до доступности альтернативного действия.
    :vartype alt_action_duration: int
    """

    token: str
    code_length: int
    request_max_duration: int
    request_count_left: int
    alt_action_duration: int


class Token(CamelModel):
    """Токен авторизации или регистрации.

    :ivar token: Значение токена.
    :vartype token: str
    """

    token: str


class TokenAttrs(BaseModel):
    """Набор токенов, возвращенных после проверки кода или пароля.

    :ivar login: Токен входа.
    :vartype login: Token | None
    :ivar register_token: Токен регистрации.
    :vartype register_token: Token | None
    """

    login: Token | None = Field(None, alias="LOGIN")
    register_token: Token | None = Field(None, alias="REGISTER")


class PasswordChallenge(CamelModel):
    """Запрос дополнительной проверки паролем.

    :ivar track_id: ID проверки.
    :vartype track_id: str
    :ivar hint: Подсказка пароля.
    :vartype hint: str | None
    """

    track_id: str
    hint: str | None = None


class CheckCodeResponse(CamelModel):
    """Ответ на проверку кода подтверждения.

    :ivar token_attrs: Токены, доступные после проверки.
    :vartype token_attrs: TokenAttrs
    :ivar password_challenge: Данные проверки паролем, если она нужна.
    :vartype password_challenge: PasswordChallenge | None
    """

    token_attrs: TokenAttrs = Field(default_factory=lambda: TokenAttrs.model_validate({}))
    password_challenge: PasswordChallenge | None = None

    @property
    def login_token(self) -> str | None:
        """Возвращает токен входа.

        :returns: Токен входа или ``None``, если сервер его не вернул.
        :rtype: str | None
        """
        return self.token_attrs.login.token if self.token_attrs.login else None

    @property
    def register_token(self) -> str | None:
        """Возвращает токен регистрации.

        :returns: Токен регистрации или ``None``, если сервер его не вернул.
        :rtype: str | None
        """
        if not self.token_attrs.register_token:
            return None
        return self.token_attrs.register_token.token


class CheckPasswordResponse(CamelModel):
    """Ответ на проверку пароля.

    :ivar token_attrs: Токены, доступные после проверки.
    :vartype token_attrs: TokenAttrs
    :ivar error: Ошибка проверки.
    :vartype error: str | None
    """

    token_attrs: TokenAttrs = Field(default_factory=lambda: TokenAttrs.model_validate({}))
    error: str | None = None

    @property
    def login_token(self) -> str | None:
        """Возвращает токен входа.

        :returns: Токен входа или ``None``, если сервер его не вернул.
        :rtype: str | None
        """
        return self.token_attrs.login.token if self.token_attrs.login else None


class RequestQrResponse(CamelModel):
    """Ответ на запрос QR-авторизации.

    :ivar expires_at: Время истечения QR-кода в формате Unix time.
    :vartype expires_at: int
    :ivar polling_interval: Интервал проверки статуса.
    :vartype polling_interval: int
    :ivar qr_link: Ссылка для QR-кода.
    :vartype qr_link: str
    :ivar track_id: ID QR-авторизации.
    :vartype track_id: str
    :ivar ttl: Время жизни QR-кода.
    :vartype ttl: int
    """

    expires_at: int
    polling_interval: int
    qr_link: str
    track_id: str
    ttl: int


class QrStatus(CamelModel):
    """Статус QR-авторизации.

    :ivar expires_at: Время истечения QR-кода в формате Unix time.
    :vartype expires_at: int
    :ivar login_available: Доступен ли вход.
    :vartype login_available: bool | None
    """

    expires_at: int
    login_available: bool | None = None


class CheckQrResponse(CamelModel):
    """Ответ на проверку статуса QR-авторизации.

    :ivar status: Статус QR-авторизации.
    :vartype status: QrStatus
    """

    status: QrStatus


class ConfirmRegistrationResponse(CamelModel):
    """Ответ Max после регистрации нового аккаунта.

    :ivar user_token: Внутренний ID зарегистрированного пользователя.
    :vartype user_token: int
    :ivar profile: Профиль зарегистрированного аккаунта.
    :vartype profile: Profile
    :ivar token_type: Тип выданного токена.
    :vartype token_type: AuthType
    :ivar token: Токен входа для новой сессии.
    :vartype token: str
    """

    user_token: int
    profile: Profile
    token_type: AuthType
    token: str
