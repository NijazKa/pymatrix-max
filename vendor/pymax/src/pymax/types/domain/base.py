from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Базовая модель с поддержкой camelCase alias-имен.

    Модель разрешает заполнение полей как по Python-именам, так и по alias,
    автоматически строит camelCase alias и допускает дополнительные поля.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        arbitrary_types_allowed=True,
        extra="allow",
    )
