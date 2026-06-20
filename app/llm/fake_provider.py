from __future__ import annotations

import json
from typing import Any

from app.llm.provider import LLMRequest, LLMResponse, LLMUsage, model_tier_for_task


_TURN_CHOICES_BY_PACING_STAGE: dict[str, tuple[dict[str, str], ...]] = {
    "setup": (
        {"id": "choice_1", "label": "稳住现场，补全关键细节", "risk": "low"},
        {"id": "choice_2", "label": "接近可能的盟友，换取第一层信息", "risk": "medium"},
        {"id": "choice_3", "label": "绕开明面规则，确认隐藏入口", "risk": "high"},
    ),
    "pressure": (
        {"id": "choice_1", "label": "守住已有线索，先稳住身边人", "risk": "low"},
        {"id": "choice_2", "label": "用可控代价试探对方反应", "risk": "medium"},
        {"id": "choice_3", "label": "抢在对手前打乱当前局面", "risk": "high"},
    ),
    "reveal": (
        {"id": "choice_1", "label": "把两条线索并在一起验证", "risk": "low"},
        {"id": "choice_2", "label": "向可靠角色摊开部分真相", "risk": "medium"},
        {"id": "choice_3", "label": "跟随最危险的线索追到源头", "risk": "high"},
    ),
    "turning_point": (
        {"id": "choice_1", "label": "收束证据，准备进入下一章", "risk": "low"},
        {"id": "choice_2", "label": "逼关键人物当场表态", "risk": "medium"},
        {"id": "choice_3", "label": "赌上身份撕开本章真正缺口", "risk": "high"},
    ),
}

_PACING_STAGE_LABELS: dict[str, str] = {
    "setup": "铺垫",
    "pressure": "加压",
    "reveal": "揭示",
    "turning_point": "转折",
}

_PACING_STAGE_NARRATIVE_LINES: dict[str, str] = {
    "setup": "先把场景秩序、人物站位和第一条线索摆清楚，不急着给答案。",
    "pressure": "让行动代价落到关系、资源或身份上，逼角色显露真实态度。",
    "reveal": "让几条线索互相咬合，露出更深原因或隐藏动机。",
    "turning_point": "把本章压力收束成方向明确的后果，并打开下一章问题。",
}


class FakeLLMProvider:
    name = "fake"

    def __init__(
        self,
        *,
        fast_model: str = "fake-fast",
        quality_model: str = "fake-quality",
    ) -> None:
        self.fast_model = fast_model
        self.quality_model = quality_model

    def generate(self, request: LLMRequest) -> LLMResponse:
        content = self._content_for_request(request)
        raw_text = json.dumps(content, ensure_ascii=False, sort_keys=True)
        input_tokens = self._estimate_tokens(
            " ".join(message.content for message in request.messages)
        )

        return LLMResponse(
            provider=self.name,
            model=self._model_for_task(request),
            task_type=request.task_type,
            content=content,
            usage=LLMUsage(
                input_tokens=input_tokens,
                output_tokens=self._estimate_tokens(raw_text),
                estimated=True,
            ),
            latency_ms=0,
            raw_text=raw_text,
            fallback_used=False,
        )

    def _model_for_task(self, request: LLMRequest) -> str:
        if model_tier_for_task(request.task_type) == "quality":
            return self.quality_model

        return self.fast_model

    def _content_for_request(self, request: LLMRequest) -> dict[str, Any]:
        if request.task_type == "story_bible_generation":
            return self._story_bible_payload(request.metadata)
        if request.task_type == "chapter_outline_generation":
            return self._chapter_outline_payload()
        if request.task_type in ("normal_turn_generation", "json_repair"):
            return self._turn_generation_payload(request.metadata)
        if request.task_type == "state_extraction":
            return {"state_patch": self._state_patch()}
        if request.task_type == "summary_generation":
            return {
                "short_summary": "Fake provider 生成了一段稳定摘要。",
                "long_summary_append": "本回合保留关键线索、角色态度和下一步目标。",
            }
        if request.task_type == "safety_classification":
            return {
                "safe": True,
                "reason": "fake provider deterministic safe output",
            }
        if request.task_type == "ending_generation":
            return {
                "ending_narrative": "Fake provider 为故事收束出一个可验证的结局。",
                "state_patch": self._state_patch(chapter_progress_delta=0),
                "safety": {
                    "safe": True,
                    "reason": "fake provider deterministic safe output",
                },
            }

        raise ValueError(f"Unsupported fake LLM task type: {request.task_type}")

    def _story_bible_payload(self, metadata: dict[str, Any]) -> dict[str, Any]:
        protagonist_name = str(metadata.get("protagonist_name", "主角"))
        template_name = str(metadata.get("template_name", "原创长篇"))
        main_goal = str(metadata.get("protagonist_main_goal", "完成当前目标"))

        return {
            "title": f"{template_name}测试开局",
            "opening_narrative": (
                f"{protagonist_name}站在命运的第一处岔路前，眼前的场景没有急着给出答案，"
                "而是先把压力、旁观者和一条不该出现的线索同时推到他面前。\n\n"
                f"他的目标仍然清楚：{main_goal}。但现在的问题不是立刻赢下一次交锋，"
                "而是判断谁在制造这场交锋、谁在旁观中藏起真实立场。\n\n"
                "当环境里的细节和人物反应慢慢合在一起，第一章的入口才真正打开："
                "下一步会决定他先抓住线索、争取同盟，还是直接撕开危险缺口。"
            ),
            "story_bible": {
                "world_rules": ["行动必须影响状态。", "剧情必须保持原创。"],
                "tone": "热血、悬念、成长",
                "forbidden_moves": ["不得复刻已有作品", "不得跳过核心冲突"],
                "major_factions": [
                    {
                        "name": "测试阵营",
                        "goal": "推动第一章冲突",
                        "attitude": "testing",
                    }
                ],
                "main_characters": [
                    {
                        "id": "npc_001",
                        "name": "测试引路人",
                        "role": "mentor_or_witness",
                        "personality": "冷静、谨慎",
                        "secret": "知道第一章冲突源头",
                        "relationship_to_player": "尚未信任主角",
                    }
                ],
            },
            "plot_plan": self._chapter_outline_payload()["plot_plan"],
            "initial_state_patch": {},
            "choices": [
                {"id": "choice_1", "label": "先观察局势", "risk": "low"},
                {"id": "choice_2", "label": "主动试探对方", "risk": "medium"},
                {"id": "choice_3", "label": "直接逼近危险源", "risk": "high"},
            ],
        }

    def _chapter_outline_payload(self) -> dict[str, Any]:
        return {
            "plot_plan": {
                "total_chapters": 8,
                "chapters": [
                    {
                        "index": 1,
                        "title": "命运开局",
                        "goal": "让主角进入核心冲突",
                        "required_outcome": "主角获得继续行动的线索",
                        "possible_branches": ["观察", "试探", "冒险"],
                        "cliffhanger": "真正威胁显露。",
                    }
                ],
            }
        }

    def _turn_generation_payload(self, metadata: dict[str, Any]) -> dict[str, Any]:
        protagonist_name = str(metadata.get("protagonist_name", "主角"))
        player_action = str(metadata.get("player_action", "继续观察局势"))
        pacing_stage = str(metadata.get("chapter_pacing_stage", "setup"))
        pacing_directive = _PACING_STAGE_NARRATIVE_LINES.get(
            pacing_stage,
            _PACING_STAGE_NARRATIVE_LINES["setup"],
        )
        pacing_label = _PACING_STAGE_LABELS.get(pacing_stage, "铺垫")

        return {
            "narrative": (
                f"{protagonist_name}围绕「{player_action}」推进一幕，"
                "但这一幕不再只用一句话交代结果。场景先出现可观察的变化，"
                "旁观者或关键角色随之调整态度，主角也必须重新判断自己手里的信息。\n\n"
                "压力没有立刻爆发，而是沿着环境细节慢慢收紧：某个物件的位置、"
                "某句没有说完的话、某个突然沉默的人，都让当前行动产生了后果。\n\n"
                f"这一页承担的是{pacing_label}节奏：{pacing_directive} "
                "直到这些线索收束到一起，局势才停在真正会影响后续走向的关键分歧前。"
            ),
            "choices": list(
                _TURN_CHOICES_BY_PACING_STAGE.get(
                    pacing_stage,
                    _TURN_CHOICES_BY_PACING_STAGE["setup"],
                )
            ),
            "state_patch": self._state_patch(),
            "memory_update": {
                "new_facts": ["fake provider 生成了一个稳定回合"],
                "open_threads": ["确认真正威胁的来源"],
                "resolved_threads": [],
            },
            "safety": {
                "safe": True,
                "reason": "fake provider deterministic safe output",
            },
        }

    def _state_patch(self, *, chapter_progress_delta: int = 1) -> dict[str, Any]:
        return {
            "active_goal": None,
            "short_summary_append": "Fake provider 推进了当前场景。",
            "relationships": {
                "npc_001": {
                    "affinity_delta": 1,
                    "trust_delta": 0,
                    "status": None,
                }
            },
            "inventory_add": [],
            "inventory_remove_ids": [],
            "stats_delta": {
                "danger": 1,
                "reputation": 0,
                "power": 0,
                "health": 0,
            },
            "flags_set": {"fake_provider_turn": True},
            "chapter_progress_delta": chapter_progress_delta,
        }

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
