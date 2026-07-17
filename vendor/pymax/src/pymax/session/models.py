from pydantic import BaseModel, Field

from pymax.types.domain.sync import SyncState


class SessionInfo(BaseModel):
    token: str
    device_id: str
    phone: str
    mt_instance_id: str = ""
    sync: SyncState = Field(default_factory=SyncState)
