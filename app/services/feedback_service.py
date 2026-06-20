from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from app.schemas.feedback import FeedbackRequest


@dataclass(frozen=True)
class FeedbackRecord:
    feedback_id: UUID
    device_id: UUID
    story_id: UUID
    turn_id: Optional[UUID]
    rating: str
    reason: str
    free_text: Optional[str]
    created_at: str


_feedback_records: list[FeedbackRecord] = []


def submit_feedback(request: FeedbackRequest) -> FeedbackRecord:
    record = FeedbackRecord(
        feedback_id=uuid4(),
        device_id=request.device_id,
        story_id=request.story_id,
        turn_id=request.turn_id,
        rating=request.rating,
        reason=request.reason,
        free_text=request.free_text,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _feedback_records.append(record)
    return record


def list_feedback_records() -> list[FeedbackRecord]:
    return list(_feedback_records)


def clear_feedback_records() -> None:
    _feedback_records.clear()
