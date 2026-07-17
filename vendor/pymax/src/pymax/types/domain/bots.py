from .base import CamelModel


class InitData(CamelModel):
    """Начальные данные web app-бота.

    :ivar query_id: ID запроса инициализации.
    :vartype query_id: str
    :ivar url: URL для открытия web app-бота.
    :vartype url: str
    """

    query_id: str
    url: str
