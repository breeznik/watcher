from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.models import StatusEnum


class WatcherBase(BaseModel):
    url: str
    phrase: str
    interval_minutes: int = Field(ge=1, le=1440)
    emails: str = ""
    enabled: bool = True


class WatcherCreate(WatcherBase):
    pass


class WatcherUpdate(WatcherBase):
    pass


class WatcherOut(WatcherBase):
    id: int
    last_check_at: Optional[datetime] = None
    last_status: Optional[StatusEnum] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LogOut(BaseModel):
    id: int
    watcher_id: int
    checked_at: datetime
    status: StatusEnum
    error_message: Optional[str] = None
    email_sent: bool = False
    email_error: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)