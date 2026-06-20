from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from pydantic import ValidationError

from app.api.errors import AppError
from app.core.config import Settings, get_settings
from app.llm.ledger import LLMCallLedger, default_llm_call_ledger
from app.llm.openai_compatible_provider import OpenAICompatibleProviderError
from app.llm.provider_factory import build_llm_provider_from_settings
from app.llm.quota import InMemoryLLMQuotaPolicy, LLMQuotaError
from app.llm.router import InMemoryLLMRouter, LLMRouterSelectionError
from app.llm.story_opening import StoryOpeningValidationError
from app.schemas.stories import (
    CreateStoryRequest,
    CreateStoryResponse,
    GetStoryResponse,
    ListStoriesResponse,
    PlayTurnRequest,
    PlayTurnResponse,
)
from app.services.cloudflare_story_store import (
    list_device_stories_from_cloudflare_store,
    load_story_from_cloudflare_store,
    save_story_to_cloudflare_store,
)
from app.services.story_service import (
    ProviderTurnGenerationError,
    StoryProviderFactory,
    create_story_from_settings,
    play_turn_from_settings,
)

router = APIRouter(tags=["stories"])


async def get_story_settings() -> Settings:
    return get_settings()


async def get_story_provider_factory() -> StoryProviderFactory:
    return build_llm_provider_from_settings


async def get_story_llm_call_ledger() -> LLMCallLedger:
    return default_llm_call_ledger


async def get_story_llm_router() -> Optional[InMemoryLLMRouter]:
    return None


async def get_story_llm_quota_policy() -> Optional[InMemoryLLMQuotaPolicy]:
    return None


@router.get("/stories", response_model=ListStoriesResponse)
async def get_stories(request: Request, device_id: UUID) -> ListStoriesResponse:
    return ListStoriesResponse(
        stories=await list_device_stories_from_cloudflare_store(
            _story_store(request),
            device_id,
        )
    )


@router.post("/stories", response_model=CreateStoryResponse)
async def post_story(
    request_context: Request,
    request: CreateStoryRequest,
    settings: Settings = Depends(get_story_settings),
    provider_factory: StoryProviderFactory = Depends(get_story_provider_factory),
    ledger: LLMCallLedger = Depends(get_story_llm_call_ledger),
    llm_router: Optional[InMemoryLLMRouter] = Depends(get_story_llm_router),
    quota_policy: Optional[InMemoryLLMQuotaPolicy] = Depends(
        get_story_llm_quota_policy
    ),
) -> CreateStoryResponse:
    try:
        story = create_story_from_settings(
            request,
            settings=settings,
            provider_factory=provider_factory,
            ledger=ledger,
            router=llm_router,
            quota_policy=quota_policy,
        )
    except (
        LLMQuotaError,
        OpenAICompatibleProviderError,
        LLMRouterSelectionError,
        StoryOpeningValidationError,
        ValidationError,
    ) as exc:
        raise _story_generation_unavailable(exc) from exc

    if story is None:
        raise AppError(
            status_code=404,
            code="template_not_found",
            message="Story template was not found.",
            details={"template_id": request.template_id},
        )

    await save_story_to_cloudflare_store(_story_store(request_context), story)

    return CreateStoryResponse(
        story_id=story.story_id,
        title=story.title,
        opening_narrative=story.opening_narrative,
        current_state=story.current_state,
        choices=story.choices,
    )


def _story_generation_unavailable(
    exc: (
        OpenAICompatibleProviderError
        | LLMQuotaError
        | LLMRouterSelectionError
        | StoryOpeningValidationError
        | ValidationError
    ),
) -> AppError:
    reason = "invalid_provider_response"
    if isinstance(exc, OpenAICompatibleProviderError):
        reason = exc.failure.error_code
    elif isinstance(exc, LLMQuotaError):
        reason = exc.failure.error_code
    elif isinstance(exc, LLMRouterSelectionError):
        reason = exc.failure.error_code

    return AppError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="story_generation_unavailable",
        message="Story generation is temporarily unavailable.",
        details={"reason": reason},
    )


@router.get("/stories/{story_id}", response_model=GetStoryResponse)
async def get_story_by_id(request: Request, story_id: UUID) -> GetStoryResponse:
    story = await load_story_from_cloudflare_store(_story_store(request), story_id)
    if story is None:
        raise AppError(
            status_code=404,
            code="story_not_found",
            message="Story was not found.",
            details={"story_id": str(story_id)},
        )

    return GetStoryResponse(
        story_id=story.story_id,
        title=story.title,
        current_state=story.current_state,
        latest_turns=story.latest_turns,
    )


@router.post("/stories/{story_id}/turns", response_model=PlayTurnResponse)
async def post_story_turn(
    request_context: Request,
    story_id: UUID,
    request: PlayTurnRequest,
    settings: Settings = Depends(get_story_settings),
    provider_factory: StoryProviderFactory = Depends(get_story_provider_factory),
    ledger: LLMCallLedger = Depends(get_story_llm_call_ledger),
    llm_router: Optional[InMemoryLLMRouter] = Depends(get_story_llm_router),
    quota_policy: Optional[InMemoryLLMQuotaPolicy] = Depends(
        get_story_llm_quota_policy
    ),
) -> PlayTurnResponse:
    story = await load_story_from_cloudflare_store(
        _story_store(request_context),
        story_id,
    )
    if story is None or story.device_id != request.device_id:
        raise AppError(
            status_code=404,
            code="story_not_found",
            message="Story was not found.",
            details={"story_id": str(story_id)},
        )

    if request.input_type == "free_text":
        user_text = (request.user_text or "").strip()
        if not user_text:
            raise AppError(
                status_code=400,
                code="missing_user_text",
                message="Free-text turn requires user_text.",
                details={},
            )

    try:
        turn = play_turn_from_settings(
            story,
            request,
            settings=settings,
            provider_factory=provider_factory,
            ledger=ledger,
            router=llm_router,
            quota_policy=quota_policy,
        )
    except (
        OpenAICompatibleProviderError,
        LLMQuotaError,
        LLMRouterSelectionError,
        ProviderTurnGenerationError,
        ValidationError,
    ) as exc:
        raise _turn_generation_unavailable(exc) from exc

    if turn is None:
        choice_id = request.choice_id if request.input_type == "choice" else None
        raise AppError(
            status_code=400,
            code="invalid_choice",
            message="Choice was not available for this story.",
            details={"choice_id": choice_id},
        )

    await save_story_to_cloudflare_store(_story_store(request_context), story)

    return turn


def _story_store(request: Request) -> object | None:
    return getattr(request.app.state, "storycat_state", None)


def _turn_generation_unavailable(
    exc: (
        OpenAICompatibleProviderError
        | LLMQuotaError
        | LLMRouterSelectionError
        | ProviderTurnGenerationError
        | ValidationError
    ),
) -> AppError:
    reason = "invalid_provider_response"
    if isinstance(exc, OpenAICompatibleProviderError):
        reason = exc.failure.error_code
    elif isinstance(exc, LLMQuotaError):
        reason = exc.failure.error_code
    elif isinstance(exc, LLMRouterSelectionError):
        reason = exc.failure.error_code
    elif isinstance(exc, ProviderTurnGenerationError):
        reason = _provider_turn_failure_reason(exc)

    return AppError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="turn_generation_unavailable",
        message="Turn generation is temporarily unavailable.",
        details={"reason": reason},
    )


def _provider_turn_failure_reason(exc: ProviderTurnGenerationError) -> str:
    result = exc.result
    if result.quota_failure is not None:
        return result.quota_failure.error_code
    if result.router_selection_failure is not None:
        return result.router_selection_failure.error_code
    if result.error_code is not None:
        return result.error_code

    return "provider_unavailable"
