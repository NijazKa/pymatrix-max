from pymax.api.models import CamelModel


class RequestInitDataPayload(CamelModel):
    bot_id: int
    chat_id: int | None = None
    start_param: str | None = None
