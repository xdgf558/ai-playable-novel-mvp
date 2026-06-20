from uuid import UUID

from pydantic import BaseModel, Field


class DeviceSessionRequest(BaseModel):
    device_id: UUID
    app_version: str = Field(min_length=1, max_length=32)
    locale: str = Field(default="zh-Hans", min_length=2, max_length=16)


class DeviceSessionResponse(BaseModel):
    user_id: UUID
    device_id: UUID
    daily_turn_limit: int
    turns_used_today: int
