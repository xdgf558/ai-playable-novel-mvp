from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    device_id: UUID
    story_id: UUID
    turn_id: Optional[UUID] = None
    rating: Literal["thumbs_up", "thumbs_down", "neutral"]
    reason: str = Field(min_length=1, max_length=120)
    free_text: Optional[str] = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    status: Literal["ok"] = "ok"
