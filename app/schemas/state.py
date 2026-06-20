from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.stories import ProtagonistProfile


class StoryFactionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    goal: str = Field(min_length=1, max_length=160)
    attitude: str = Field(min_length=1, max_length=40)


class StoryCharacterState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=80)
    personality: str = Field(min_length=1, max_length=160)
    secret: str = Field(min_length=1, max_length=200)
    relationship_to_player: str = Field(min_length=1, max_length=160)


class StoryBibleState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    world_rules: list[str] = Field(min_length=1)
    tone: str = Field(min_length=1, max_length=120)
    forbidden_moves: list[str] = Field(min_length=1)
    major_factions: list[StoryFactionState] = Field(min_length=1)
    main_characters: list[StoryCharacterState] = Field(min_length=1)


class ChapterPlanState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=80)
    goal: str = Field(min_length=1, max_length=200)
    required_outcome: str = Field(min_length=1, max_length=200)
    possible_branches: list[str] = Field(min_length=1)
    cliffhanger: str = Field(min_length=1, max_length=200)


class PlotPlanState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_chapters: int = Field(ge=1)
    chapters: list[ChapterPlanState] = Field(min_length=1)


class RelationshipState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affinity: int
    trust: int
    status: str = Field(min_length=1, max_length=80)


class InventoryItemState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=200)
    quantity: int = Field(default=1, ge=1)


class PlayerStatsState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    danger: int = Field(ge=0)
    reputation: int
    power: int = Field(ge=0)
    health: int = Field(ge=0, le=100)


class RelationshipPatchState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affinity_delta: int = 0
    trust_delta: int = 0
    status: Optional[str] = Field(default=None, max_length=80)


class PlayerStatsDeltaState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    danger: int = 0
    reputation: int = 0
    power: int = 0
    health: int = 0


class TurnStatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_goal: Optional[str] = Field(default=None, max_length=200)
    short_summary_append: str = Field(default="", max_length=2000)
    relationships: dict[str, RelationshipPatchState] = Field(default_factory=dict)
    inventory_add: list[InventoryItemState] = Field(default_factory=list)
    inventory_remove_ids: list[str] = Field(default_factory=list)
    stats_delta: PlayerStatsDeltaState = Field(default_factory=PlayerStatsDeltaState)
    flags_set: dict[str, Any] = Field(default_factory=dict)
    chapter_progress_delta: int = 0


class StoryState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: UUID
    locale: str = Field(min_length=2, max_length=16)
    template_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    protagonist: ProtagonistProfile
    story_bible: StoryBibleState
    plot_plan: PlotPlanState
    current_chapter_index: int = Field(ge=1)
    current_scene_index: int = Field(ge=1)
    active_goal: str = Field(min_length=1, max_length=200)
    short_summary: str = Field(min_length=1)
    long_summary: str = Field(min_length=1)
    relationships: dict[str, RelationshipState] = Field(min_length=1)
    inventory: list[InventoryItemState] = Field(default_factory=list)
    stats: PlayerStatsState
    flags: dict[str, Any]
    turn_count: int = Field(ge=0)
    updated_at: datetime
