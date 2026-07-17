from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, arbitrary_types_allowed=True
    )

    def to_payload(self) -> dict:
        return self.model_dump(by_alias=True, exclude_none=True)
