import asyncio
from uuid import uuid4

from app.schemas.stories import CreateStoryRequest
from app.services.cloudflare_story_store import (
    list_device_stories_from_cloudflare_store,
    load_story_from_cloudflare_store,
    save_story_to_cloudflare_store,
)
from app.services.story_service import clear_stories, create_story


class FakeCloudflareKV:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def put(self, key: str, value: str) -> None:
        self.values[key] = value


def test_cloudflare_story_store_round_trips_story_and_device_index() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(
        {
            "device_id": str(uuid4()),
            "template_id": "xianxia_rise",
            "locale": "zh-Hans",
            "protagonist": {
                "name": "林澈",
                "pronouns": "他",
                "age_band": "adult",
                "personality": ["冷静", "不服输"],
                "starting_role": "被宗门轻视的外门弟子",
                "main_goal": "查清家族没落真相",
                "special_ability": "能听见灵气裂隙中的低语",
            },
            "tone": "热血、悬念、成长",
            "content_rating": "teen",
        }
    )
    story = create_story(request)
    assert story is not None

    kv = FakeCloudflareKV()
    asyncio.run(save_story_to_cloudflare_store(kv, story))

    clear_stories()
    restored_story = asyncio.run(
        load_story_from_cloudflare_store(kv, story.story_id)
    )
    assert restored_story is not None
    assert restored_story.story_id == story.story_id
    assert restored_story.choices[0].id == "choice_1"

    clear_stories()
    summaries = asyncio.run(
        list_device_stories_from_cloudflare_store(kv, story.device_id)
    )
    assert [summary.story_id for summary in summaries] == [story.story_id]
