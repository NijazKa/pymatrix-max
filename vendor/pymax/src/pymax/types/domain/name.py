from .base import CamelModel


class Name(CamelModel):
    """Имя пользователя.

    :ivar name: Полное отображаемое имя.
    :vartype name: str | None
    :ivar first_name: Имя.
    :vartype first_name: str | None
    :ivar last_name: Фамилия.
    :vartype last_name: str | None
    :ivar type: Тип имени.
    :vartype type: str | None
    """

    name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    type: str | None = None
