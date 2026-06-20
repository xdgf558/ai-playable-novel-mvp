from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ActionRedirect:
    code: str
    narrative_template: str

    def render_narrative(self, protagonist_name: str) -> str:
        return self.narrative_template.format(protagonist_name=protagonist_name)


_ACTION_REDIRECTS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "unsafe_action",
        (
            "自杀",
            "轻生",
            "自残",
            "性侵",
            "强奸",
            "未成年性",
            "制作炸弹",
            "制毒",
            "抢银行",
            "suicide",
            "self-harm",
            "make a bomb",
        ),
        (
            "这个动作会把故事带向不适合当前作品安全边界的方向。"
            "{protagonist_name}及时收住念头，把冲动改成更稳妥的试探："
            "先保护自己、确认线索，再寻找不伤及现实规则的破局方式。"
        ),
    ),
    (
        "copyright_ip",
        (
            "哈利波特",
            "霍格沃茨",
            "漫威",
            "蜘蛛侠",
            "火影",
            "鸣人",
            "海贼王",
            "路飞",
            "harry potter",
            "hogwarts",
            "marvel",
            "naruto",
            "one piece",
        ),
        (
            "这个设定可能涉及已有作品或角色。{protagonist_name}把灵感收束回原创世界："
            "保留学院、试炼或阵营冲突的气氛，但不借用已有角色与世界名。"
        ),
    ),
    (
        "impossible_action",
        (
            "跳到大结局",
            "直接通关",
            "秒杀所有",
            "立刻成仙",
            "瞬间无敌",
            "毁灭世界",
            "召唤核弹",
            "skip to the ending",
            "beat everyone instantly",
        ),
        (
            "这个动作超出了当前章节能成立的行动边界。"
            "{protagonist_name}没有强行扭断因果，而是把目标压回眼前："
            "先从可验证的线索入手，寻找下一步突破口。"
        ),
    ),
)


def validate_free_text_action(user_text: str) -> Optional[ActionRedirect]:
    normalized_text = user_text.strip().casefold()
    for code, patterns, narrative_template in _ACTION_REDIRECTS:
        if any(pattern.casefold() in normalized_text for pattern in patterns):
            return ActionRedirect(
                code=code,
                narrative_template=narrative_template,
            )

    return None
