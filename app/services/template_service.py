from __future__ import annotations

from app.schemas.templates import StoryTemplate


_ZH_HANS_TEMPLATES: tuple[StoryTemplate, ...] = (
    StoryTemplate(
        id="xianxia_rise",
        name="修仙逆袭",
        genre="修仙",
        short_description="从边缘小人物开始，踏入宗门、秘境和天命之争。",
        tags=["升级", "宗门", "秘境", "爽文"],
        recommended_tone=["热血", "暗线", "成长"],
    ),
    StoryTemplate(
        id="apocalypse_base",
        name="末世基地",
        genre="末世生存",
        short_description="文明崩塌后，组建队伍、寻找物资，并守住最后的基地。",
        tags=["生存", "基地", "团队", "抉择"],
        recommended_tone=["紧张", "群像", "希望"],
    ),
    StoryTemplate(
        id="urban_ability",
        name="都市异能",
        genre="都市异能",
        short_description="普通人觉醒能力后，卷入隐藏在都市背后的势力斗争。",
        tags=["异能", "都市", "调查", "成长"],
        recommended_tone=["悬念", "热血", "隐秘"],
    ),
    StoryTemplate(
        id="infinity_trial",
        name="无限试炼",
        genre="无限流",
        short_description="被拉入危险的规则世界，在一次次试炼中寻找逃离真相。",
        tags=["规则", "求生", "副本", "反转"],
        recommended_tone=["高压", "智斗", "惊险"],
    ),
    StoryTemplate(
        id="detective_mystery",
        name="悬疑探案",
        genre="悬疑探案",
        short_description="一桩怪案牵出更深的阴谋，线索、嫌疑人与真相彼此纠缠。",
        tags=["线索", "推理", "阴谋", "反转"],
        recommended_tone=["冷峻", "悬疑", "克制"],
    ),
)


def list_templates(locale: str = "zh-Hans") -> list[StoryTemplate]:
    if locale != "zh-Hans":
        return list(_ZH_HANS_TEMPLATES)

    return list(_ZH_HANS_TEMPLATES)


def get_template_by_id(
    template_id: str,
    locale: str = "zh-Hans",
) -> StoryTemplate | None:
    for template in list_templates(locale=locale):
        if template.id == template_id:
            return template

    return None
