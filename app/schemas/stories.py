from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProtagonistProfile(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    pronouns: str = Field(min_length=1, max_length=16)
    age_band: Literal["adult"] = "adult"
    personality: list[str] = Field(min_length=1, max_length=6)
    starting_role: str = Field(min_length=1, max_length=80)
    main_goal: str = Field(min_length=1, max_length=120)
    special_ability: str = Field(min_length=1, max_length=120)


class CreateStoryRequest(BaseModel):
    device_id: UUID
    template_id: str = Field(min_length=1, max_length=64)
    locale: str = Field(default="zh-Hans", min_length=2, max_length=16)
    protagonist: ProtagonistProfile
    tone: str = Field(default="热血、悬念、成长", min_length=1, max_length=80)
    content_rating: Literal["teen"] = "teen"


class StoryChoice(BaseModel):
    id: str
    label: str
    risk: Literal["low", "medium", "high"]


class CreateStoryResponse(BaseModel):
    story_id: UUID
    title: str
    opening_narrative: str
    current_state: dict[str, Any]
    choices: list[StoryChoice]


class GetStoryResponse(BaseModel):
    story_id: UUID
    title: str
    current_state: dict[str, Any]
    latest_turns: list[dict[str, Any]]


class StorySummary(BaseModel):
    story_id: UUID
    title: str
    template_id: str
    current_chapter_index: int
    turn_count: int
    updated_at: str


class ListStoriesResponse(BaseModel):
    stories: list[StorySummary]


class PlayTurnRequest(BaseModel):
    device_id: UUID
    input_type: Literal["choice", "free_text"]
    choice_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    user_text: Optional[str] = Field(default=None, max_length=500)


class ChapterProgress(BaseModel):
    current_chapter_index: int
    current_scene_index: int
    progress_percent: int


class TurnUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    model: str


class PlayTurnResponse(BaseModel):
    turn_id: UUID
    story_id: UUID
    narrative: str
    choices: list[StoryChoice]
    state: dict[str, Any]
    chapter_progress: ChapterProgress
    usage: TurnUsage
    warnings: list[str]
