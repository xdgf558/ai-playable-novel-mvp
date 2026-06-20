from dataclasses import dataclass
from uuid import UUID, uuid4

from app.core.config import get_settings


@dataclass(frozen=True)
class DeviceSession:
    user_id: UUID
    device_id: UUID
    daily_turn_limit: int
    turns_used_today: int


_sessions_by_device_id: dict[UUID, DeviceSession] = {}


def create_or_reuse_device_session(device_id: UUID) -> DeviceSession:
    existing_session = _sessions_by_device_id.get(device_id)
    if existing_session is not None:
        return existing_session

    settings = get_settings()
    session = DeviceSession(
        user_id=uuid4(),
        device_id=device_id,
        daily_turn_limit=settings.daily_turn_limit,
        turns_used_today=0,
    )
    _sessions_by_device_id[device_id] = session
    return session


def clear_device_sessions() -> None:
    _sessions_by_device_id.clear()
