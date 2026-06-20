from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID, uuid4

from app.core.config import Settings, get_settings
from app.llm.gateway import LLMGenerationResult, generate_normal_turn_with_repair
from app.llm.ledger import LLMCallLedger, LLMCallLedgerEntry
from app.llm.parser import LLMParseResult
from app.llm.provider import LLMProvider, LLMRequest
from app.llm.provider_factory import build_llm_provider_from_settings
from app.llm.quota import InMemoryLLMQuotaPolicy
from app.llm.router import InMemoryLLMRouter
from app.llm.story_opening import (
    StoryOpeningGenerationResult,
    StoryOpeningValidationError,
    assemble_story_state_from_opening_payload,
    generate_story_opening,
)
from app.schemas.stories import (
    ChapterProgress,
    CreateStoryRequest,
    PlayTurnResponse,
    PlayTurnRequest,
    StoryChoice,
    StorySummary,
    TurnUsage,
)
from app.services.state_manager import (
    apply_choice_turn_state_update,
    apply_free_text_turn_state_update,
    apply_generated_turn_state_patch,
    validate_story_state,
)
from app.services.safety_filter import ActionRedirect, validate_free_text_action
from app.services.template_service import get_template_by_id


@dataclass(frozen=True)
class StoryRecord:
    story_id: UUID
    device_id: UUID
    template_id: str
    title: str
    opening_narrative: str
    current_state: dict
    choices: list[StoryChoice]
    latest_turns: list[dict]


_stories_by_id: dict[UUID, StoryRecord] = {}

StoryProviderFactory = Callable[[Settings], LLMProvider]


class ProviderTurnGenerationError(RuntimeError):
    def __init__(self, result: LLMGenerationResult) -> None:
        self.result = result
        super().__init__(result.error_message or "Provider turn generation failed.")


_TEMPLATE_TITLES: dict[str, str] = {
    "xianxia_rise": "裂隙听灵者",
    "apocalypse_base": "灰烬基地",
    "urban_ability": "霓虹暗涌",
    "infinity_trial": "第七条规则",
    "detective_mystery": "雨夜旧案",
}


_OPENING_CONTEXT: dict[str, str] = {
    "xianxia_rise": "青石试炼台上，外门弟子的名字被一个个念过，唯独你的木牌被执事压在掌心。",
    "apocalypse_base": "广播里的最后一段求救信号戛然而止，仓库外的铁门被什么东西缓慢撞响。",
    "urban_ability": "凌晨的高架桥下，霓虹灯在积水里碎成一片，你第一次听见能力苏醒时的低鸣。",
    "infinity_trial": "倒计时从天花板渗出的红光里开始，陌生房间的墙上写着第一条生存规则。",
    "detective_mystery": "旧城区的雨下了一整夜，案发现场只剩半枚烧焦的纸符和一只停摆的怀表。",
}


_CHOICES_BY_TEMPLATE: dict[str, list[StoryChoice]] = {
    "xianxia_rise": [
        StoryChoice(id="choice_1", label="低头忍耐，先观察局势", risk="low"),
        StoryChoice(id="choice_2", label="当众反击，争取试炼机会", risk="medium"),
        StoryChoice(id="choice_3", label="私下寻找掌事长老", risk="medium"),
    ],
    "apocalypse_base": [
        StoryChoice(id="choice_1", label="加固仓库大门，守住物资", risk="low"),
        StoryChoice(id="choice_2", label="带人冲出去查看撞门声", risk="high"),
        StoryChoice(id="choice_3", label="搜索广播设备，确认信号来源", risk="medium"),
    ],
    "urban_ability": [
        StoryChoice(id="choice_1", label="隐藏异常，先离开现场", risk="low"),
        StoryChoice(id="choice_2", label="追踪暗处观察你的人", risk="medium"),
        StoryChoice(id="choice_3", label="测试刚觉醒的能力边界", risk="high"),
    ],
    "infinity_trial": [
        StoryChoice(id="choice_1", label="逐字记录墙上的规则", risk="low"),
        StoryChoice(id="choice_2", label="立刻检查房间出口", risk="medium"),
        StoryChoice(id="choice_3", label="质问其他试炼者的身份", risk="medium"),
    ],
    "detective_mystery": [
        StoryChoice(id="choice_1", label="封存现场，先整理线索", risk="low"),
        StoryChoice(id="choice_2", label="追问第一发现人", risk="medium"),
        StoryChoice(id="choice_3", label="冒雨去查纸符来源", risk="medium"),
    ],
}


_NEXT_CHOICE_VARIANTS: tuple[tuple[str, str, str], ...] = (
    (
        "顺着线索继续试探",
        "主动暴露一点底牌换取情报",
        "直接逼近真正的危险源",
    ),
    (
        "退到暗处整理刚得到的线索",
        "借一个小破绽试探对方反应",
        "当面逼问最可疑的人",
    ),
    (
        "先稳住同伴，确认退路",
        "用半真半假的消息换取协助",
        "冒险潜入异动最强的中心",
    ),
    (
        "放慢节奏，观察环境变化",
        "主动提出交易，换取下一步入口",
        "抢在对手前引爆当前矛盾",
    ),
    (
        "保护关键物品，等待局势露出破绽",
        "假装顺从，诱导对方透露目的",
        "切断敌人的后路，逼出幕后人物",
    ),
    (
        "回看上一幕细节，寻找遗漏线索",
        "向可靠角色坦白一部分计划",
        "独自追进危险区域验证猜想",
    ),
    (
        "保持低调，先修正当前目标",
        "把新线索交给盟友共同判断",
        "公开挑战威胁源头的权威",
    ),
    (
        "收束行动，确保自己没有暴露",
        "设置一个小陷阱观察谁会上钩",
        "直接触碰禁忌线索换取突破",
    ),
)

_PACING_CHOICE_VARIANTS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "setup": (
        (
            "稳住现场，补全关键细节",
            "接近可能的盟友，换取第一层信息",
            "绕开明面规则，确认隐藏入口",
        ),
        (
            "先保护身份，不让对方看清底牌",
            "用一个小问题试探旁观者立场",
            "直接触碰最反常的线索",
        ),
        (
            "退半步整理人物关系",
            "主动给出有限情报争取信任",
            "冒险验证规则背后的漏洞",
        ),
    ),
    "pressure": (
        (
            "守住已有线索，先稳住身边人",
            "用可控代价试探对方反应",
            "抢在对手前打乱当前局面",
        ),
        (
            "把危险压低，确认退路",
            "借势提出交换，逼对方表态",
            "追着压力源继续推进",
        ),
        (
            "暂缓冲突，观察谁最急躁",
            "把半真半假的消息放出去",
            "公开挑战当前规则",
        ),
    ),
    "reveal": (
        (
            "把两条线索并在一起验证",
            "向可靠角色摊开部分真相",
            "跟随最危险的线索追到源头",
        ),
        (
            "回看细节，找出被遮住的证据",
            "让盟友协助确认关键矛盾",
            "强行撬开沉默者守住的秘密",
        ),
        (
            "暂时隐藏发现，等待对方露破绽",
            "用新线索交换更深层情报",
            "直接逼近幕后安排者",
        ),
    ),
    "turning_point": (
        (
            "收束证据，准备进入下一章",
            "逼关键人物当场表态",
            "赌上身份撕开本章真正缺口",
        ),
        (
            "保护核心线索，稳住转折后的局面",
            "把同盟推到台前共同承担后果",
            "顺着裂口追进更大的危险",
        ),
        (
            "先保住退路，带着答案离开现场",
            "当众交换条件，换取下一章入口",
            "直接引爆本章隐藏矛盾",
        ),
    ),
}

_PACING_STAGE_DETAILS: dict[str, dict[str, str]] = {
    "setup": {
        "label": "setup",
        "narrative": (
            "这一页还不急着爆出答案，而是先把场景里的秩序、旁观者的位置、"
            "以及主角能抓住的第一条线摆清楚。"
        ),
        "provider": (
            "Set up the scene and character stakes. Prioritize atmosphere, roles, "
            "first clues, and the first pressure point. Do not resolve the chapter."
        ),
    },
    "pressure": {
        "label": "pressure",
        "narrative": (
            "压力开始从外部传到人身上：角色立场变得更清楚，行动代价也开始"
            "真正落到关系、资源或身份上。"
        ),
        "provider": (
            "Escalate cost and opposition. Show consequences and reactions, but "
            "keep the core mystery or conflict moving rather than resolving it."
        ),
    },
    "reveal": {
        "label": "reveal",
        "narrative": (
            "几个细节终于互相咬合，露出比眼前冲突更深的一层原因；"
            "新的选择不再只是行动方式，而是在决定相信谁、牺牲什么。"
        ),
        "provider": (
            "Reveal a meaningful connection between clues. Let the player see a "
            "deeper cause, hidden motive, or changed relationship before choosing."
        ),
    },
    "turning_point": {
        "label": "turning_point",
        "narrative": (
            "局面收束到本章的转折口，之前铺下的压力必须给出一个方向；"
            "下一步会改变主角进入下一段故事时带走的同盟、敌意或线索。"
        ),
        "provider": (
            "Drive toward a chapter turn. Pay off earlier pressure, force a clear "
            "directional consequence, and open the next chapter question."
        ),
    },
}

_PACING_STAGE_FIRST_CHOICE_SCENE_INDEX: dict[str, int] = {
    "setup": 2,
    "pressure": 3,
    "reveal": 5,
    "turning_point": 6,
}

_OPENING_PAGE_STAKES: dict[str, str] = {
    "xianxia_rise": (
        "如果今天只是失去试炼名额，你还能等下一次；但木牌被压住的方式"
        "像是有人故意要把你从宗门记录里抹掉，这背后牵着家族没落的旧线。"
    ),
    "apocalypse_base": (
        "门外的撞击也许只是感染体，也许是最后一批能证明救援仍存在的人。"
        "一旦判断失误，仓库里剩下的食物、信任和秩序都会一起崩掉。"
    ),
    "urban_ability": (
        "能力觉醒本身不是最危险的事，危险的是有人比你更早知道它会出现，"
        "并且已经把你的朋友、住处和日常路线都纳入观察。"
    ),
    "infinity_trial": (
        "规则看似公平，却故意没有说明违规的边界。你必须在别人测试你之前，"
        "先判断谁会成为同盟，谁会把你当成第一块试错石。"
    ),
    "detective_mystery": (
        "这起命案最棘手的地方不是缺少线索，而是每一条线索都像被人切掉一半。"
        "如果你选错追查方向，真正的凶手会借雨夜把旧案再次埋回去。"
    ),
}

_TEMPLATE_TURN_BEATS: dict[str, tuple[str, ...]] = {
    "xianxia_rise": (
        "执事袖口露出一缕不该属于外门试炼的黑色灵纹，台下几名弟子同时安静下来。",
        "被压住的木牌忽然发烫，像是有人隔着石台把一段旧誓约推到你掌心。",
        "山门钟声提前响起，禁地方向掠过一道细得几乎看不见的剑光。",
        "神秘引路人终于开口，只提醒你一句：真正的试炼从来不在台面上。",
        "围观弟子开始分成两派，有人想看你跌落，也有人悄悄替你让出一条路。",
        "执事脸上的镇定第一次裂开，因为你刚才的动作碰到了他藏起来的漏洞。",
    ),
    "apocalypse_base": (
        "铁门后的撞击声突然变成三短一长，像是有人在废墟里用最后的力气求救。",
        "仓库灯管闪了两下，地面灰尘里浮出一串新鲜拖痕，方向正通向备用水箱。",
        "无线电里传来半截坐标，和基地地图上被涂黑的区域正好重合。",
        "巡逻队带回一只沾血的臂章，证明门外的不只是感染体。",
        "孩子们躲进货架后，老发电机却在这时停了一拍，所有声音都变得刺耳。",
        "远处楼顶亮起手电信号，对方似乎知道你们今晚一定会做出选择。",
    ),
    "urban_ability": (
        "霓虹灯在积水里忽明忽暗，你的影子却比身体慢了半拍才动。",
        "便利店玻璃门上映出第二个观察者，他看见你回头后立刻消失在人群里。",
        "手机收到一条没有号码的短信，里面只有你刚刚没有说出口的念头。",
        "城市高架下的风声忽然低下去，能力像细线一样牵住了某个陌生人的谎言。",
        "街角监控同时转向你，说明暗处的组织已经不打算继续旁观。",
        "你身边的朋友发来求助定位，而地点正是能力第一次失控的地方。",
    ),
    "infinity_trial": (
        "墙上的规则褪下一层灰，露出被前一批试炼者划掉的半句警告。",
        "倒计时没有减少，反而多出一行隐藏条件，所有人的呼吸都乱了一瞬。",
        "房间中央的门缝里滚出一枚号码牌，上面刻着你的名字缩写。",
        "有人试图撒谎，却被系统提示音当场打断，试炼的真正惩罚开始显形。",
        "地面格子重新排列，安全路线变成了只有你能看懂的短暂图案。",
        "天花板红光暗下去三秒，足够你看见监控后面还有另一双眼睛。",
    ),
    "detective_mystery": (
        "雨水从窗缝渗进来，刚好浸湿那半枚纸符上被烧掉的最后一笔。",
        "停摆怀表突然走了一格，时间指向每个人证词里都避开的三分钟。",
        "第一发现人端茶时手指发颤，杯底留下了和现场泥痕相同的细沙。",
        "旧案卷宗里夹着一张新照片，照片背后却写着今晚才出现的房间号。",
        "山庄电灯熄灭前，你看见镜面里有个人没有站在他声称的位置。",
        "嫌疑人们开始互相指认，但每句话都像是在保护同一个更大的秘密。",
    ),
}

_TEMPLATE_TURN_DETAILS: dict[str, tuple[str, ...]] = {
    "xianxia_rise": (
        "石台边缘的灵纹一寸寸暗下去，旁观者的议论也随之变轻。王大锤没有急着把结果说出口，而是先看见了执事指节上那道细小裂痕：那不是紧张，而是某种阵法反噬留下的痕迹。",
        "风从山门方向压下来，带着潮湿的铁锈味。原本只是围观看热闹的弟子开始退开半步，仿佛所有人都意识到，这一场试炼已经不只是外门名额的争夺。",
        "神秘引路人的目光短暂落在王大锤身上，又很快移开。他没有出手，却用沉默证明了一件事：如果王大锤继续往前走，接下来牵出的不会只是一个人的秘密。",
    ),
    "apocalypse_base": (
        "仓库里的人同时停住呼吸，连老发电机的抖动声都显得刺耳。你能感觉到大家在等一个可以相信的判断，但每一双眼睛背后都藏着饥饿、疲惫和不愿再失去同伴的恐惧。",
        "门外的动静没有立刻逼近，反而像是在故意等待。备用水箱旁的灰尘被蹭开一条细线，说明有人比感染体更早来过，而且熟悉基地内部的路线。",
        "孩子们被护到货架后面，几个成年人却开始低声争执。资源、路线、救援信号和未知危险挤在同一刻，任何一个决定都可能让基地少活过一个夜晚。",
    ),
    "urban_ability": (
        "街边霓虹在雨水里碎成几层颜色，你的能力像一根看不见的细线，轻轻绷住人群中某个不该出现的目光。那个人没有靠近，却精准地避开了所有监控死角。",
        "手机屏幕还亮着，刚收到的信息没有署名，却比熟人更了解你的下一步。你意识到觉醒能力不是偶然，它像一把钥匙，而城市里已经有人等这把钥匙很久了。",
        "朋友的求助定位停在高架桥下，那里白天车流不断，夜里却像被城市遗忘。你能继续装作普通人，但能力带来的异常已经开始反过来改变身边人的命运。",
    ),
    "infinity_trial": (
        "墙上的规则没有解释更多，只把沉默压在每个人肩上。有人开始重新计算格子的安全顺序，也有人把怀疑藏进眼神里，试炼真正危险的部分正在从环境转向人心。",
        "倒计时跳动得很慢，慢到足够让每个人听见自己的呼吸。你注意到上一批试炼者留下的划痕并不完整，像是有人在写完关键提醒前被迫停手。",
        "号码牌滚到脚边时，其他试炼者的站位立刻变了。没有人承认害怕，但你清楚，从这一刻起，规则不再只是房间里的文字，也会变成人与人之间的陷阱。",
    ),
    "detective_mystery": (
        "雨声盖住了山庄走廊里的脚步，壁灯在风里轻轻晃动。你把刚得到的线索重新排了一遍，发现每个人的证词都能解释一部分现场，却没人能解释那三分钟的空白。",
        "纸符上的残痕被雨水泡开，露出一截几乎看不见的朱砂线。它不像普通迷信道具，更像是有人故意留下的半个签名，等着你把它和旧案连起来。",
        "嫌疑人们开始互相指认，声音越来越急，但越急越像在避开同一个名字。真正的突破口不在谁说了什么，而在谁一直没有被任何人提起。",
    ),
}

_TEMPLATE_TURN_KEYPOINTS: dict[str, tuple[str, ...]] = {
    "xianxia_rise": (
        "等这一连串细节落定，王大锤才意识到，眼前已经不是立刻反击或退让的小事，而是要决定自己以什么方式踏入宗门暗线。",
        "局面终于收束成一个会影响后续章节的关键分歧：稳住身份、换取同盟，或直接撕开对方藏住的漏洞。",
        "这一页停在真正的门槛前。再往前一步，王大锤得到的就不只是线索，也会是第一批明确的敌人。",
    ),
    "apocalypse_base": (
        "等众人的争执暂时压下去，你才看清真正的问题：不是门外有什么，而是基地还能不能在恐惧里保持一个共同方向。",
        "局势逼近一个关键分歧：保守守住现有资源、冒险验证信号，或先找出内部泄露路线的人。",
        "这一刻的选择会改变基地接下来几天的秩序，也会决定还有多少人愿意继续相信你的判断。",
    ),
    "urban_ability": (
        "当异常信号、求助定位和暗处观察者连成一条线，你明白自己已经站在普通生活和能力世界的交界处。",
        "关键不再是能力能做什么，而是你准备让谁知道、让谁靠近，以及让谁误以为你还没有察觉。",
        "这一页停在城市阴影打开之前。下一步会决定你是继续隐藏，还是主动把暗处的人引出来。",
    ),
    "infinity_trial": (
        "等规则、号码牌和众人的反应互相咬合，你终于看见这个房间真正想测试的不是智力，而是信任会在压力下碎成什么形状。",
        "关键分歧已经出现：按规则求稳、利用人心破局，或冒险验证隐藏条件的代价。",
        "这一页停在试炼第一次露出獠牙的位置。下一步会让你得到信息，也会让系统更清楚地看见你。",
    ),
    "detective_mystery": (
        "当纸符、旧案和证词空白互相对上，你知道案件已经越过普通谋杀的边界，开始碰到山庄里每个人都不愿承认的过去。",
        "关键分歧不是继续收集更多琐碎线索，而是决定先撬开哪一个沉默的人、哪一段旧案，或哪一个被保护的房间。",
        "这一页停在真相露出边角的时候。再推进一步，凶手未必会现身，但一定会开始反击。",
    ),
}

_RISK_NARRATIVE_FRAGMENTS: dict[str, str] = {
    "low": "没有急着把底牌推上桌，而是先把危险压在可控范围内",
    "medium": "把主动权往前推了一寸，也让对方不得不暴露更多反应",
    "high": "直接撕开最危险的缺口，短时间内换来了更清晰的真相",
}

_OPENING_PAGE_DETAILS: dict[str, str] = {
    "xianxia_rise": (
        "试炼台四周挤满了外门弟子，香灰、雨水和低声嘲笑混在一起。"
        "有人等着看你出丑，也有人把视线藏在人群后面，像是在确认某个早就布好的局。"
    ),
    "apocalypse_base": (
        "仓库外的街区已经断电三天，楼群像一排沉默的黑影。"
        "剩下的人围着物资清单争执，每个人都知道，只靠锁门撑不到下一次救援。"
    ),
    "urban_ability": (
        "雨夜的城市还在照常运转，便利店、地铁口和高架桥都亮着冷白的灯。"
        "只有你知道，刚才那一瞬间，世界像慢了一拍，而某个陌生人看见了这一点。"
    ),
    "infinity_trial": (
        "陌生房间没有窗，墙上的规则像刚被刻出来一样新。"
        "其他试炼者故作镇定地观察彼此，但每个人都在偷偷确认谁最可能先违反规则。"
    ),
    "detective_mystery": (
        "山庄被雨夜封住，电话线和山路同时断掉。"
        "死者房间里的灯还亮着，桌上的半枚纸符被压在杯底，像有人故意留下一个不完整的答案。"
    ),
}


def _opening_narrative_for_request(
    request: CreateStoryRequest,
    *,
    template_id: str,
) -> str:
    detail = _OPENING_PAGE_DETAILS.get(
        template_id,
        "故事从一个看似普通却已经失衡的场景开始，周围每个人都在等待主角先露出破绽。",
    )
    stakes = _OPENING_PAGE_STAKES.get(
        template_id,
        "第一幕真正重要的不是立刻赢下冲突，而是看清谁在推动它、谁在回避它，以及主角下一步会因此欠下什么代价。",
    )
    protagonist = request.protagonist
    return (
        f"{_OPENING_CONTEXT[template_id]}你叫{protagonist.name}，"
        f"仍记得自己的目标：{protagonist.main_goal}。\n\n"
        f"{detail}{protagonist.starting_role}这个身份没有给你太多余地，"
        f"但你的特殊能力「{protagonist.special_ability}」让你比旁人更早察觉到，"
        "眼前的麻烦只是第一层表象。\n\n"
        f"{stakes}这让眼前的开局不再只是一次试探，"
        "而是一条会把你带进长篇主线的细线：它一端拴着当前的困境，"
        "另一端拴着还没有露面的真正对手。\n\n"
        f"你没有立刻行动，而是把自己的性格里最可靠的部分压到心底："
        f"{'、'.join(protagonist.personality)}。它们让你没有被第一波压力带着走，"
        "也让你看见周围人真正关心的并不是公平，而是谁能在混乱里先拿到主动权。\n\n"
        "这一页不是让你立刻做一道选择题，而是把你推到长篇故事的第一处门槛前："
        "你需要先看清局势里谁在试探、谁在隐瞒、谁会因为你的下一步行动而改变立场。"
    )


def create_story(request: CreateStoryRequest) -> StoryRecord | None:
    template = get_template_by_id(request.template_id, locale=request.locale)
    if template is None:
        return None

    story_id = uuid4()
    title = _TEMPLATE_TITLES.get(template.id, f"{template.name}开局")
    choices = list(_CHOICES_BY_TEMPLATE[template.id])
    protagonist = request.protagonist.model_dump()
    updated_at = datetime.now(timezone.utc).isoformat()
    opening_narrative = _opening_narrative_for_request(request, template_id=template.id)
    current_state = {
        "story_id": str(story_id),
        "locale": request.locale,
        "template_id": template.id,
        "title": title,
        "protagonist": protagonist,
        "story_bible": {
            "world_rules": [
                f"这是一个{template.genre}故事，节奏围绕{template.name}展开。",
                "主角行动会影响关系、资源和章节目标。",
                "每章按铺垫、加压、揭示、转折推进，选择只出现在关键分歧处。",
            ],
            "tone": request.tone,
            "forbidden_moves": ["不得导入或复刻已有小说情节", "不得使用真实 LLM"],
            "major_factions": [
                {
                    "name": template.name,
                    "goal": "推动第一章冲突形成",
                    "attitude": "testing",
                }
            ],
            "main_characters": [
                {
                    "id": "npc_001",
                    "name": "神秘引路人",
                    "role": "mentor_or_witness",
                    "personality": "克制、观察力强",
                    "secret": "知道第一章冲突的真正来源",
                    "relationship_to_player": "尚未信任主角",
                }
            ],
        },
        "plot_plan": {
            "total_chapters": 8,
            "chapters": [
                {
                    "index": 1,
                    "title": "命运开局",
                    "goal": "从身份压力铺垫到第一次站队或冒险行动",
                    "required_outcome": "主角获得继续追查主线威胁的线索和第一层关系反馈",
                    "possible_branches": [choice.label for choice in choices],
                    "cliffhanger": "真正的威胁在第一轮选择后显露。",
                },
                {
                    "index": 2,
                    "title": "暗线初显",
                    "goal": "把第一章留下的威胁推进成可追查的暗线",
                    "required_outcome": "主角确认下一阶段的核心对手、可靠同盟或关键物证",
                    "possible_branches": ["保守验证线索", "联合关键角色", "冒险逼近幕后"],
                    "cliffhanger": "更大的幕后力量开始注意主角。",
                }
            ],
        },
        "current_chapter_index": 1,
        "current_scene_index": 1,
        "active_goal": request.protagonist.main_goal,
        "short_summary": opening_narrative,
        "long_summary": opening_narrative,
        "relationships": {
            "npc_001": {"affinity": 0, "trust": 0, "status": "unknown"}
        },
        "inventory": [],
        "stats": {"danger": 10, "reputation": 0, "power": 1, "health": 100},
        "flags": {"fake_mode": True, "opening_created": True},
        "turn_count": 0,
        "updated_at": updated_at,
    }
    validate_story_state(current_state)
    story = StoryRecord(
        story_id=story_id,
        device_id=request.device_id,
        template_id=template.id,
        title=title,
        opening_narrative=opening_narrative,
        current_state=current_state,
        choices=choices,
        latest_turns=[],
    )
    _stories_by_id[story_id] = story
    return story


def _next_choices_for_state(state: dict) -> list[StoryChoice]:
    pacing_stage = _chapter_pacing_stage_for_state(state)
    variants = _PACING_CHOICE_VARIANTS.get(pacing_stage, _NEXT_CHOICE_VARIANTS)
    variant_index = _choice_variant_index_for_state(
        state,
        pacing_stage=pacing_stage,
        variant_count=len(variants),
    )
    labels = variants[variant_index]
    return [
        StoryChoice(id="choice_1", label=labels[0], risk="low"),
        StoryChoice(id="choice_2", label=labels[1], risk="medium"),
        StoryChoice(id="choice_3", label=labels[2], risk="high"),
    ]


def _choice_variant_index_for_state(
    state: dict,
    *,
    pacing_stage: str,
    variant_count: int,
) -> int:
    chapter_index = int(state.get("current_chapter_index") or 1)
    scene_index = int(state.get("current_scene_index") or 1)
    first_scene_index = _PACING_STAGE_FIRST_CHOICE_SCENE_INDEX.get(pacing_stage, 1)
    stage_local_index = max(scene_index - first_scene_index, 0)
    return (stage_local_index + max(chapter_index - 1, 0)) % variant_count


def _chapter_pacing_stage_for_state(state: dict) -> str:
    scene_index = int(state.get("current_scene_index") or 1)
    if scene_index <= 2:
        return "setup"
    if scene_index <= 4:
        return "pressure"
    if scene_index <= 5:
        return "reveal"
    return "turning_point"


def _chapter_pacing_context_for_state(state: dict) -> dict[str, str]:
    stage = _chapter_pacing_stage_for_state(state)
    details = _PACING_STAGE_DETAILS[stage]
    return {
        "stage": details["label"],
        "narrative_directive": details["narrative"],
        "provider_directive": details["provider"],
    }


def _chapter_pacing_line_for_state(state: dict) -> str:
    return _PACING_STAGE_DETAILS[_chapter_pacing_stage_for_state(state)]["narrative"]


def _turn_beat_for_state(state: dict) -> str:
    template_id = str(state.get("template_id") or "")
    beats = _TEMPLATE_TURN_BEATS.get(template_id) or _TEMPLATE_TURN_BEATS[
        "xianxia_rise"
    ]
    turn_count = int(state.get("turn_count") or 0)
    chapter_index = int(state.get("current_chapter_index") or 1)
    return beats[(turn_count + chapter_index - 1) % len(beats)]


def _turn_detail_for_state(state: dict) -> str:
    template_id = str(state.get("template_id") or "")
    details = _TEMPLATE_TURN_DETAILS.get(template_id) or _TEMPLATE_TURN_DETAILS[
        "xianxia_rise"
    ]
    turn_count = int(state.get("turn_count") or 0)
    chapter_index = int(state.get("current_chapter_index") or 1)
    return details[(turn_count + chapter_index - 1) % len(details)]


def _turn_keypoint_for_state(state: dict) -> str:
    template_id = str(state.get("template_id") or "")
    keypoints = _TEMPLATE_TURN_KEYPOINTS.get(template_id) or _TEMPLATE_TURN_KEYPOINTS[
        "xianxia_rise"
    ]
    turn_count = int(state.get("turn_count") or 0)
    chapter_index = int(state.get("current_chapter_index") or 1)
    return keypoints[(turn_count + chapter_index - 1) % len(keypoints)]


def _turn_reflection_for_state(state: dict, protagonist_name: str) -> str:
    active_goal = str(state.get("active_goal") or "当前目标")
    pacing_line = _chapter_pacing_line_for_state(state)
    return (
        f"{protagonist_name}没有急着把这一切简化成输赢，而是把刚发生的变化"
        f"同自己的目标「{active_goal}」重新对照。真正有用的信息往往藏在反应里："
        "谁先沉默，谁急着解释，谁在危险出现前就已经知道退路。"
        "如果此刻只追求立刻占上风，后面更深的线索反而会被惊走。"
        f"{pacing_line}"
    )


def _choice_turn_narrative(state: dict, selected_choice: StoryChoice) -> str:
    protagonist_name = state["protagonist"]["name"]
    risk_fragment = _RISK_NARRATIVE_FRAGMENTS[selected_choice.risk]
    beat = _turn_beat_for_state(state)
    detail = _turn_detail_for_state(state).replace("王大锤", protagonist_name)
    reflection = _turn_reflection_for_state(state, protagonist_name)
    keypoint = _turn_keypoint_for_state(state).replace("王大锤", protagonist_name)
    return (
        f"你选择了「{selected_choice.label}」。{protagonist_name}{risk_fragment}。"
        f"{beat}\n\n"
        f"{detail}\n\n"
        f"{reflection}\n\n"
        f"{keypoint}"
    )


def _free_text_turn_narrative(state: dict, cleaned_user_text: str) -> str:
    protagonist_name = state["protagonist"]["name"]
    bridge = "" if cleaned_user_text[-1] in "。！？!?." else "，"
    beat = _turn_beat_for_state(state)
    detail = _turn_detail_for_state(state).replace("王大锤", protagonist_name)
    reflection = _turn_reflection_for_state(state, protagonist_name)
    keypoint = _turn_keypoint_for_state(state).replace("王大锤", protagonist_name)
    return (
        f"你没有选择既定路线，而是把想法落成行动：「{cleaned_user_text}」{bridge}"
        f"{protagonist_name}把这个临场决定嵌进当前局势里。{beat}\n\n"
        f"{detail}\n\n"
        f"{reflection}\n\n"
        f"{keypoint}"
    )


def create_story_with_llm_provider(
    request: CreateStoryRequest,
    *,
    provider: LLMProvider,
    updated_at: str | None = None,
    ledger: LLMCallLedger | None = None,
    router: InMemoryLLMRouter | None = None,
    quota_policy: InMemoryLLMQuotaPolicy | None = None,
) -> StoryRecord | None:
    template = get_template_by_id(request.template_id, locale=request.locale)
    if template is None:
        return None

    story_id = uuid4()
    try:
        opening = generate_story_opening(
            provider,
            request,
            template=template,
            router=router,
            quota_policy=quota_policy,
        )
    except StoryOpeningValidationError as exc:
        failed_entry = _record_failed_story_opening_ledger_entry(
            ledger=ledger,
            error=exc,
        )
        _record_story_opening_router_usage(router=router, entry=failed_entry)
        _record_story_opening_quota_usage(
            quota_policy=quota_policy,
            entry=failed_entry,
        )
        raise

    ledger_entry = _record_story_opening_ledger_entry(ledger=ledger, opening=opening)
    _record_story_opening_router_usage(router=router, entry=ledger_entry)
    _record_story_opening_quota_usage(
        quota_policy=quota_policy,
        entry=ledger_entry,
    )
    current_state = assemble_story_state_from_opening_payload(
        opening.payload,
        story_id=story_id,
        story_request=request,
        template=template,
        updated_at=updated_at,
    )
    story = StoryRecord(
        story_id=story_id,
        device_id=request.device_id,
        template_id=template.id,
        title=opening.payload.title,
        opening_narrative=opening.payload.opening_narrative,
        current_state=current_state,
        choices=list(opening.payload.choices),
        latest_turns=[],
    )
    _stories_by_id[story_id] = story
    return story


def create_story_from_settings(
    request: CreateStoryRequest,
    *,
    settings: Settings | None = None,
    provider_factory: StoryProviderFactory = build_llm_provider_from_settings,
    updated_at: str | None = None,
    ledger: LLMCallLedger | None = None,
    router: InMemoryLLMRouter | None = None,
    quota_policy: InMemoryLLMQuotaPolicy | None = None,
) -> StoryRecord | None:
    resolved_settings = settings or get_settings()
    if resolved_settings.llm_fake_mode:
        return create_story(request)

    if get_template_by_id(request.template_id, locale=request.locale) is None:
        return None

    provider = provider_factory(resolved_settings)
    return create_story_with_llm_provider(
        request,
        provider=provider,
        updated_at=updated_at,
        ledger=ledger,
        router=router,
        quota_policy=quota_policy,
    )


def _record_story_opening_ledger_entry(
    *,
    ledger: LLMCallLedger | None,
    opening: StoryOpeningGenerationResult,
) -> LLMCallLedgerEntry | None:
    if ledger is None:
        return None

    return ledger.record_response(
        response=opening.response,
        attempt_type="initial",
        parse_result=LLMParseResult(
            ok=True,
            task_type=opening.response.task_type,
            content=opening.payload.model_dump(),
        ),
    )


def _record_failed_story_opening_ledger_entry(
    *,
    ledger: LLMCallLedger | None,
    error: StoryOpeningValidationError,
) -> LLMCallLedgerEntry | None:
    if ledger is None:
        return None

    return ledger.record_response(
        response=error.response,
        attempt_type="initial",
        parse_result=LLMParseResult(
            ok=False,
            task_type=error.response.task_type,
            error_code="invalid_schema",
            error_message=str(error.validation_error),
        ),
    )


def _record_story_opening_router_usage(
    *,
    router: InMemoryLLMRouter | None,
    entry: LLMCallLedgerEntry | None,
) -> None:
    if router is None or entry is None:
        return

    router.record_usage_from_ledger_entry(entry)


def _record_story_opening_quota_usage(
    *,
    quota_policy: InMemoryLLMQuotaPolicy | None,
    entry: LLMCallLedgerEntry | None,
) -> None:
    if quota_policy is None or entry is None:
        return

    quota_policy.record_usage_from_ledger_entry(entry)


def get_story(story_id: UUID) -> StoryRecord | None:
    return _stories_by_id.get(story_id)


def story_record_to_payload(story: StoryRecord) -> dict[str, Any]:
    return {
        "story_id": str(story.story_id),
        "device_id": str(story.device_id),
        "template_id": story.template_id,
        "title": story.title,
        "opening_narrative": story.opening_narrative,
        "current_state": story.current_state,
        "choices": [choice.model_dump(mode="json") for choice in story.choices],
        "latest_turns": story.latest_turns,
    }


def restore_story_record(payload: dict[str, Any]) -> StoryRecord:
    story = StoryRecord(
        story_id=UUID(payload["story_id"]),
        device_id=UUID(payload["device_id"]),
        template_id=payload["template_id"],
        title=payload["title"],
        opening_narrative=payload["opening_narrative"],
        current_state=payload["current_state"],
        choices=[
            StoryChoice.model_validate(choice_payload)
            for choice_payload in payload["choices"]
        ],
        latest_turns=list(payload["latest_turns"]),
    )
    _stories_by_id[story.story_id] = story
    return story


def list_stories_for_device(device_id: UUID) -> list[StorySummary]:
    summaries: list[StorySummary] = []
    for story in _stories_by_id.values():
        if story.device_id != device_id:
            continue

        state = story.current_state
        summaries.append(
            StorySummary(
                story_id=story.story_id,
                title=story.title,
                template_id=story.template_id,
                current_chapter_index=state["current_chapter_index"],
                turn_count=state["turn_count"],
                updated_at=state["updated_at"],
            )
        )

    return summaries


def play_turn_from_settings(
    story: StoryRecord,
    request: PlayTurnRequest,
    *,
    settings: Settings | None = None,
    provider_factory: StoryProviderFactory = build_llm_provider_from_settings,
    ledger: LLMCallLedger | None = None,
    router: InMemoryLLMRouter | None = None,
    quota_policy: InMemoryLLMQuotaPolicy | None = None,
    updated_at: str | None = None,
) -> PlayTurnResponse | None:
    resolved_settings = settings or get_settings()

    if request.input_type == "choice":
        if request.choice_id is None:
            return None
        if resolved_settings.llm_fake_mode:
            return play_choice_turn(story, choice_id=request.choice_id)

        provider = provider_factory(resolved_settings)
        return play_choice_turn_with_llm_provider(
            story,
            choice_id=request.choice_id,
            provider=provider,
            ledger=ledger,
            router=router,
            quota_policy=quota_policy,
            updated_at=updated_at,
        )

    user_text = (request.user_text or "").strip()
    if not user_text:
        return None
    if resolved_settings.llm_fake_mode:
        return play_free_text_turn(story, user_text=user_text)

    provider = provider_factory(resolved_settings)
    return play_free_text_turn_with_llm_provider(
        story,
        user_text=user_text,
        provider=provider,
        ledger=ledger,
        router=router,
        quota_policy=quota_policy,
        updated_at=updated_at,
    )


def play_choice_turn(story: StoryRecord, choice_id: str) -> PlayTurnResponse | None:
    selected_choice = _find_choice(story.choices, choice_id)
    if selected_choice is None:
        return None

    turn_id = uuid4()
    state = story.current_state
    narrative = _choice_turn_narrative(state, selected_choice)
    previous_chapter_index = state["current_chapter_index"]
    apply_choice_turn_state_update(
        state,
        choice_id=selected_choice.id,
        choice_risk=selected_choice.risk,
        narrative=narrative,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    story.choices.clear()
    story.choices.extend(_next_choices_for_state(state))

    chapter_progress = _chapter_progress_for_state(state)
    usage = TurnUsage(input_tokens=0, output_tokens=0, model="fake-fast")
    warnings = _chapter_transition_warnings(previous_chapter_index, state)
    turn = PlayTurnResponse(
        turn_id=turn_id,
        story_id=story.story_id,
        narrative=narrative,
        choices=list(story.choices),
        state=state,
        chapter_progress=chapter_progress,
        usage=usage,
        warnings=warnings,
    )
    turn_record = {
        "turn_id": str(turn_id),
        "story_id": str(story.story_id),
        "input_type": "choice",
        "choice_id": selected_choice.id,
        "narrative": narrative,
        "choices": [choice.model_dump() for choice in story.choices],
        "created_at": state["updated_at"],
    }
    if warnings:
        turn_record["warnings"] = warnings
        turn_record["chapter_completed"] = True
        turn_record["completed_chapter_index"] = previous_chapter_index
    story.latest_turns.append(turn_record)
    return turn


def play_choice_turn_with_llm_provider(
    story: StoryRecord,
    choice_id: str,
    *,
    provider: LLMProvider,
    ledger: LLMCallLedger | None = None,
    router: InMemoryLLMRouter | None = None,
    quota_policy: InMemoryLLMQuotaPolicy | None = None,
    updated_at: str | None = None,
) -> PlayTurnResponse | None:
    selected_choice = _find_choice(story.choices, choice_id)
    if selected_choice is None:
        return None

    request = _build_choice_normal_turn_request(
        story=story,
        selected_choice=selected_choice,
    )
    result = generate_normal_turn_with_repair(
        provider,
        request,
        ledger=ledger,
        router=router,
        quota_policy=quota_policy,
    )
    if not result.ok:
        raise ProviderTurnGenerationError(result)
    if result.content is None or result.response is None:
        raise RuntimeError("Normal-turn gateway returned an incomplete success result.")

    content = result.content
    narrative = str(content["narrative"])
    generated_choices = [
        StoryChoice.model_validate(choice) for choice in content["choices"]
    ]
    turn_id = uuid4()
    state = story.current_state
    previous_chapter_index = state["current_chapter_index"]
    apply_generated_turn_state_patch(
        state,
        patch=content["state_patch"],
        narrative=narrative,
        updated_at=updated_at or datetime.now(timezone.utc).isoformat(),
    )
    state["flags"]["last_input_type"] = "choice"
    state["flags"]["last_choice_id"] = selected_choice.id
    state["flags"]["last_choice_risk"] = selected_choice.risk
    validate_story_state(state)

    story.choices.clear()
    story.choices.extend(generated_choices)

    chapter_progress = _chapter_progress_for_state(state)
    usage = TurnUsage(
        input_tokens=result.response.usage.input_tokens,
        output_tokens=result.response.usage.output_tokens,
        model=result.response.model,
    )
    warnings = _provider_turn_warnings(result) + _chapter_transition_warnings(
        previous_chapter_index,
        state,
    )
    turn = PlayTurnResponse(
        turn_id=turn_id,
        story_id=story.story_id,
        narrative=narrative,
        choices=list(story.choices),
        state=state,
        chapter_progress=chapter_progress,
        usage=usage,
        warnings=warnings,
    )
    story.latest_turns.append(
        {
            "turn_id": str(turn_id),
            "story_id": str(story.story_id),
            "input_type": "choice",
            "choice_id": selected_choice.id,
            "narrative": narrative,
            "choices": [choice.model_dump() for choice in story.choices],
            "state_patch": content["state_patch"],
            "memory_update": content["memory_update"],
            "safety": content["safety"],
            "llm": {
                "provider": result.response.provider,
                "model": result.response.model,
                "input_tokens": result.response.usage.input_tokens,
                "output_tokens": result.response.usage.output_tokens,
                "fallback_used": result.fallback_used,
                "repair_used": result.repair_used,
            },
            "created_at": state["updated_at"],
            "warnings": warnings,
        }
    )
    return turn


def play_free_text_turn_with_llm_provider(
    story: StoryRecord,
    user_text: str,
    *,
    provider: LLMProvider,
    ledger: LLMCallLedger | None = None,
    router: InMemoryLLMRouter | None = None,
    quota_policy: InMemoryLLMQuotaPolicy | None = None,
    updated_at: str | None = None,
) -> PlayTurnResponse | None:
    cleaned_user_text = user_text.strip()
    if not cleaned_user_text:
        return None

    redirect = validate_free_text_action(cleaned_user_text)
    if redirect is not None:
        return _play_redirected_free_text_turn(
            story,
            user_text=cleaned_user_text,
            redirect=redirect,
        )

    request = _build_free_text_normal_turn_request(
        story=story,
        user_text=cleaned_user_text,
    )
    result = generate_normal_turn_with_repair(
        provider,
        request,
        ledger=ledger,
        router=router,
        quota_policy=quota_policy,
    )
    if not result.ok:
        raise ProviderTurnGenerationError(result)
    if result.content is None or result.response is None:
        raise RuntimeError("Normal-turn gateway returned an incomplete success result.")

    content = result.content
    narrative = str(content["narrative"])
    generated_choices = [
        StoryChoice.model_validate(choice) for choice in content["choices"]
    ]
    turn_id = uuid4()
    state = story.current_state
    previous_chapter_index = state["current_chapter_index"]
    apply_generated_turn_state_patch(
        state,
        patch=content["state_patch"],
        narrative=narrative,
        updated_at=updated_at or datetime.now(timezone.utc).isoformat(),
    )
    state["flags"]["last_input_type"] = "free_text"
    state["flags"]["last_user_text"] = cleaned_user_text
    validate_story_state(state)

    story.choices.clear()
    story.choices.extend(generated_choices)

    chapter_progress = _chapter_progress_for_state(state)
    usage = TurnUsage(
        input_tokens=result.response.usage.input_tokens,
        output_tokens=result.response.usage.output_tokens,
        model=result.response.model,
    )
    warnings = _provider_turn_warnings(result) + _chapter_transition_warnings(
        previous_chapter_index,
        state,
    )
    turn = PlayTurnResponse(
        turn_id=turn_id,
        story_id=story.story_id,
        narrative=narrative,
        choices=list(story.choices),
        state=state,
        chapter_progress=chapter_progress,
        usage=usage,
        warnings=warnings,
    )
    story.latest_turns.append(
        {
            "turn_id": str(turn_id),
            "story_id": str(story.story_id),
            "input_type": "free_text",
            "choice_id": None,
            "user_text": cleaned_user_text,
            "narrative": narrative,
            "choices": [choice.model_dump() for choice in story.choices],
            "state_patch": content["state_patch"],
            "memory_update": content["memory_update"],
            "safety": content["safety"],
            "llm": {
                "provider": result.response.provider,
                "model": result.response.model,
                "input_tokens": result.response.usage.input_tokens,
                "output_tokens": result.response.usage.output_tokens,
                "fallback_used": result.fallback_used,
                "repair_used": result.repair_used,
            },
            "created_at": state["updated_at"],
            "warnings": warnings,
        }
    )
    return turn


def play_free_text_turn(story: StoryRecord, user_text: str) -> PlayTurnResponse:
    cleaned_user_text = user_text.strip()
    redirect = validate_free_text_action(cleaned_user_text)
    if redirect is not None:
        return _play_redirected_free_text_turn(
            story,
            user_text=cleaned_user_text,
            redirect=redirect,
        )

    turn_id = uuid4()
    state = story.current_state
    narrative = _free_text_turn_narrative(state, cleaned_user_text)
    previous_chapter_index = state["current_chapter_index"]
    apply_free_text_turn_state_update(
        state,
        user_text=cleaned_user_text,
        narrative=narrative,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    story.choices.clear()
    story.choices.extend(_next_choices_for_state(state))

    chapter_progress = _chapter_progress_for_state(state)
    usage = TurnUsage(input_tokens=0, output_tokens=0, model="fake-fast")
    warnings = _chapter_transition_warnings(previous_chapter_index, state)
    turn = PlayTurnResponse(
        turn_id=turn_id,
        story_id=story.story_id,
        narrative=narrative,
        choices=list(story.choices),
        state=state,
        chapter_progress=chapter_progress,
        usage=usage,
        warnings=warnings,
    )
    turn_record = {
        "turn_id": str(turn_id),
        "story_id": str(story.story_id),
        "input_type": "free_text",
        "choice_id": None,
        "user_text": cleaned_user_text,
        "narrative": narrative,
        "choices": [choice.model_dump() for choice in story.choices],
        "created_at": state["updated_at"],
    }
    if warnings:
        turn_record["warnings"] = warnings
        turn_record["chapter_completed"] = True
        turn_record["completed_chapter_index"] = previous_chapter_index
    story.latest_turns.append(turn_record)
    return turn


def _play_redirected_free_text_turn(
    story: StoryRecord,
    *,
    user_text: str,
    redirect: ActionRedirect,
) -> PlayTurnResponse:
    turn_id = uuid4()
    state = story.current_state
    narrative = redirect.render_narrative(state["protagonist"]["name"])
    validate_story_state(state)

    chapter_progress = _chapter_progress_for_state(state)
    usage = TurnUsage(input_tokens=0, output_tokens=0, model="fake-fast")
    warnings = [f"action_redirected:{redirect.code}"]
    turn = PlayTurnResponse(
        turn_id=turn_id,
        story_id=story.story_id,
        narrative=narrative,
        choices=list(story.choices),
        state=state,
        chapter_progress=chapter_progress,
        usage=usage,
        warnings=warnings,
    )
    story.latest_turns.append(
        {
            "turn_id": str(turn_id),
            "story_id": str(story.story_id),
            "input_type": "free_text",
            "choice_id": None,
            "user_text": user_text,
            "narrative": narrative,
            "choices": [choice.model_dump() for choice in story.choices],
            "redirected": True,
            "redirect_reason": redirect.code,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return turn


def _chapter_progress_for_state(state: dict) -> ChapterProgress:
    return ChapterProgress(
        current_chapter_index=state["current_chapter_index"],
        current_scene_index=state["current_scene_index"],
        progress_percent=min(100, state["current_scene_index"] * 11),
    )


def _chapter_transition_warnings(
    previous_chapter_index: int,
    state: dict,
) -> list[str]:
    if state["current_chapter_index"] <= previous_chapter_index:
        return []

    completed_chapter_index = state["flags"].get(
        "last_completed_chapter_index",
        previous_chapter_index,
    )
    return [f"chapter_completed:{completed_chapter_index}"]


def _provider_turn_warnings(result: LLMGenerationResult) -> list[str]:
    warnings: list[str] = []
    if result.repair_used:
        warnings.append("llm_repair_used")
    if result.fallback_used:
        warnings.append("llm_fallback_used")

    return warnings


def _find_choice(choices: list[StoryChoice], choice_id: str) -> StoryChoice | None:
    for choice in choices:
        if choice.id == choice_id:
            return choice

    return None


def _build_choice_normal_turn_request(
    *,
    story: StoryRecord,
    selected_choice: StoryChoice,
) -> LLMRequest:
    state = story.current_state
    metadata = _choice_normal_turn_metadata(
        story=story,
        selected_choice=selected_choice,
    )
    pacing_context = _chapter_pacing_context_for_state(state)
    prompt_payload = {
        "story": {
            "story_id": str(story.story_id),
            "template_id": story.template_id,
            "title": story.title,
            "current_chapter_index": state["current_chapter_index"],
            "current_scene_index": state["current_scene_index"],
            "turn_count": state["turn_count"],
            "active_goal": state["active_goal"],
            "short_summary": state["short_summary"],
            "long_summary": state["long_summary"],
            "relationships": state["relationships"],
            "inventory": state["inventory"],
            "stats": state["stats"],
            "flags": state["flags"],
        },
        "chapter_pacing": pacing_context,
        "selected_choice": selected_choice.model_dump(),
        "available_choices": [choice.model_dump() for choice in story.choices],
        "required_response": {
            "narrative": (
                "3 to 5 paragraphs, 600 to 1000 Chinese characters, with the "
                "choice consequences, scene texture, NPC/world reaction, and a "
                "true key decision point at the end. Follow chapter_pacing.stage "
                "so the turn functions as setup, pressure, reveal, or turning point."
            ),
            "choices": (
                "exactly three differentiated branch decisions: choice_1 preserves "
                "or investigates with lower risk, choice_2 negotiates or tests "
                "relationships with medium risk, choice_3 confronts or breaks "
                "through with high risk"
            ),
            "state_patch": "TurnStatePatch",
            "memory_update": "new facts and thread updates",
            "safety": "teen-safe classification",
        },
    }

    return LLMRequest(
        task_type="normal_turn_generation",
        messages=[
            {
                "role": "system",
                "content": (
                    "Generate one original teen-safe interactive novel turn. "
                    "Write a substantial page, not a short prompt: 3 to 5 "
                    "paragraphs, roughly 600 to 1000 Chinese characters. "
                    "Let the selected choice play out through concrete scene "
                    "details, character reaction, consequence, and tension "
                    "before ending on a real key decision point. "
                    "Respect the supplied chapter_pacing.stage: setup should "
                    "clarify roles and first clues, pressure should raise costs, "
                    "reveal should connect clues or motives, and turning_point "
                    "should pay off the current chapter beat while opening the "
                    "next question. The three choices should be meaningfully "
                    "different branch decisions for the next section, not "
                    "frequent micro-choices. "
                    "Return only strict json matching the normal_turn_generation schema: "
                    "narrative, exactly three choices, state_patch, memory_update, "
                    "and safety. Do not wrap the response in markdown.\n\n"
                    f"EXAMPLE JSON OUTPUT:\n{_normal_turn_json_example()}"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    prompt_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        ],
        max_output_tokens=1400,
        metadata=metadata,
    )


def _build_free_text_normal_turn_request(
    *,
    story: StoryRecord,
    user_text: str,
) -> LLMRequest:
    state = story.current_state
    metadata = _free_text_normal_turn_metadata(story=story, user_text=user_text)
    pacing_context = _chapter_pacing_context_for_state(state)
    prompt_payload = {
        "story": {
            "story_id": str(story.story_id),
            "template_id": story.template_id,
            "title": story.title,
            "current_chapter_index": state["current_chapter_index"],
            "current_scene_index": state["current_scene_index"],
            "turn_count": state["turn_count"],
            "active_goal": state["active_goal"],
            "short_summary": state["short_summary"],
            "long_summary": state["long_summary"],
            "relationships": state["relationships"],
            "inventory": state["inventory"],
            "stats": state["stats"],
            "flags": state["flags"],
        },
        "chapter_pacing": pacing_context,
        "user_action": user_text,
        "available_choices": [choice.model_dump() for choice in story.choices],
        "required_response": {
            "narrative": (
                "3 to 5 paragraphs, 600 to 1000 Chinese characters, with the "
                "free-text action consequences, scene texture, NPC/world "
                "reaction, and a true key decision point at the end. Follow "
                "chapter_pacing.stage so the turn functions as setup, pressure, "
                "reveal, or turning point."
            ),
            "choices": (
                "exactly three differentiated branch decisions: choice_1 preserves "
                "or investigates with lower risk, choice_2 negotiates or tests "
                "relationships with medium risk, choice_3 confronts or breaks "
                "through with high risk"
            ),
            "state_patch": "TurnStatePatch",
            "memory_update": "new facts and thread updates",
            "safety": "teen-safe classification",
        },
    }

    return LLMRequest(
        task_type="normal_turn_generation",
        messages=[
            {
                "role": "system",
                "content": (
                    "Generate one original teen-safe interactive novel turn for "
                    "the player's free-text action. Write a substantial page, "
                    "not a short prompt: 3 to 5 paragraphs, roughly 600 to "
                    "1000 Chinese characters. Let the free-text action play "
                    "out through concrete scene details, character reaction, "
                    "consequence, and tension before ending on a real key "
                    "decision point. Respect the supplied chapter_pacing.stage: "
                    "setup should clarify roles and first clues, pressure should "
                    "raise costs, reveal should connect clues or motives, and "
                    "turning_point should pay off the current chapter beat while "
                    "opening the next question. The three choices should be "
                    "meaningfully different branch decisions for the next section, "
                    "not frequent micro-choices. Return only strict json matching "
                    "the normal_turn_generation schema: narrative, exactly three "
                    "choices, state_patch, memory_update, and safety. Do not wrap "
                    "the response in markdown.\n\n"
                    f"EXAMPLE JSON OUTPUT:\n{_normal_turn_json_example()}"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    prompt_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        ],
        max_output_tokens=1400,
        metadata=metadata,
    )


def _normal_turn_json_example() -> str:
    example = {
        "narrative": (
            "主角顺着线索推进当前场景，先观察到环境里被忽略的细节，"
            "再看见关键角色因为他的行动产生新的反应。\n\n"
            "这一段需要写出行动的过程、代价和局势变化，而不是只用一句话概括。"
            "读者应该感觉自己读完了一页小说，而不是刚看完一个选择题题干。\n\n"
            "最后让场景自然停在真正会改变后续走向的关键分歧上，再给出三个选择。"
        ),
        "choices": [
            {"id": "choice_1", "label": "稳住现场，补全关键细节", "risk": "low"},
            {"id": "choice_2", "label": "接近可能的盟友，换取第一层信息", "risk": "medium"},
            {"id": "choice_3", "label": "绕开明面规则，确认隐藏入口", "risk": "high"},
        ],
        "state_patch": {
            "active_goal": None,
            "short_summary_append": "本回合推进了当前场景。",
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
            "flags_set": {"new_clue_found": True},
            "chapter_progress_delta": 1,
        },
        "memory_update": {
            "new_facts": ["主角发现一个新线索"],
            "open_threads": ["确认真正威胁的来源"],
            "resolved_threads": [],
        },
        "safety": {
            "safe": True,
            "reason": "teen-safe original story turn",
        },
    }
    return json.dumps(example, ensure_ascii=False, sort_keys=True)


def _choice_normal_turn_metadata(
    *,
    story: StoryRecord,
    selected_choice: StoryChoice,
) -> dict[str, Any]:
    state = story.current_state
    protagonist = state["protagonist"]
    pacing_context = _chapter_pacing_context_for_state(state)

    return {
        "story_id": str(story.story_id),
        "template_id": story.template_id,
        "title": story.title,
        "locale": state["locale"],
        "protagonist_name": protagonist["name"],
        "current_chapter_index": state["current_chapter_index"],
        "current_scene_index": state["current_scene_index"],
        "turn_count": state["turn_count"],
        "input_type": "choice",
        "choice_id": selected_choice.id,
        "choice_risk": selected_choice.risk,
        "player_action": selected_choice.label,
        "chapter_pacing_stage": pacing_context["stage"],
        "chapter_pacing_directive": pacing_context["provider_directive"],
    }


def _free_text_normal_turn_metadata(
    *,
    story: StoryRecord,
    user_text: str,
) -> dict[str, Any]:
    state = story.current_state
    protagonist = state["protagonist"]
    pacing_context = _chapter_pacing_context_for_state(state)

    return {
        "story_id": str(story.story_id),
        "template_id": story.template_id,
        "title": story.title,
        "locale": state["locale"],
        "protagonist_name": protagonist["name"],
        "current_chapter_index": state["current_chapter_index"],
        "current_scene_index": state["current_scene_index"],
        "turn_count": state["turn_count"],
        "input_type": "free_text",
        "player_action": user_text,
        "user_text": user_text,
        "chapter_pacing_stage": pacing_context["stage"],
        "chapter_pacing_directive": pacing_context["provider_directive"],
    }


def clear_stories() -> None:
    _stories_by_id.clear()
