from fastapi import APIRouter, Request

from app.api.errors import AppError
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.services.cloudflare_story_store import load_story_from_cloudflare_store
from app.services.feedback_service import submit_feedback
from app.services.story_service import get_story

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
async def post_feedback(
    request_context: Request,
    request: FeedbackRequest,
) -> FeedbackResponse:
    story = await load_story_from_cloudflare_store(
        getattr(request_context.app.state, "storycat_state", None),
        request.story_id,
    )
    if story is None:
        story = get_story(request.story_id)

    if story is None or story.device_id != request.device_id:
        raise AppError(
            status_code=404,
            code="story_not_found",
            message="Story was not found.",
            details={"story_id": str(request.story_id)},
        )

    submit_feedback(request)
    return FeedbackResponse()
