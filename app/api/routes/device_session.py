from fastapi import APIRouter

from app.schemas.device_session import DeviceSessionRequest, DeviceSessionResponse
from app.services.device_session_service import create_or_reuse_device_session

router = APIRouter(tags=["device-session"])


@router.post("/device-session", response_model=DeviceSessionResponse)
async def post_device_session(request: DeviceSessionRequest) -> DeviceSessionResponse:
    session = create_or_reuse_device_session(request.device_id)
    return DeviceSessionResponse(
        user_id=session.user_id,
        device_id=session.device_id,
        daily_turn_limit=session.daily_turn_limit,
        turns_used_today=session.turns_used_today,
    )
