from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any
from uuid import UUID

from app.schemas.stories import StorySummary
from app.services.story_service import (
    StoryRecord,
    get_story,
    list_stories_for_device,
    restore_story_record,
    story_record_to_payload,
)

_STORY_KEY_PREFIX = "story:"
_DEVICE_STORIES_KEY_PREFIX = "device-stories:"


def is_cloudflare_story_store_available(store: Any | None) -> bool:
    return store is not None


async def load_story_from_cloudflare_store(
    store: Any | None,
    story_id: UUID,
) -> StoryRecord | None:
    cached_story = get_story(story_id)
    if cached_story is not None or store is None:
        return cached_story

    raw_payload = _cloudflare_kv_text(await store.get(_story_key(story_id)))
    if raw_payload is None:
        return None

    try:
        payload = json.loads(raw_payload)
    except JSONDecodeError:
        return None

    return restore_story_record(payload)


async def save_story_to_cloudflare_store(
    store: Any | None,
    story: StoryRecord,
) -> None:
    if store is None:
        return

    await store.put(
        _story_key(story.story_id),
        json.dumps(story_record_to_payload(story), ensure_ascii=False, default=str),
    )
    await _add_story_to_device_index(store, story.device_id, story.story_id)


async def list_device_stories_from_cloudflare_store(
    store: Any | None,
    device_id: UUID,
) -> list[StorySummary]:
    if store is None:
        return list_stories_for_device(device_id)

    raw_index = _cloudflare_kv_text(await store.get(_device_stories_key(device_id)))
    if raw_index is not None:
        for story_id_text in _story_ids_from_index_payload(raw_index):
            await load_story_from_cloudflare_store(store, UUID(story_id_text))

    return list_stories_for_device(device_id)


async def _add_story_to_device_index(
    store: Any,
    device_id: UUID,
    story_id: UUID,
) -> None:
    key = _device_stories_key(device_id)
    raw_index = _cloudflare_kv_text(await store.get(key))
    story_ids = (
        _story_ids_from_index_payload(raw_index) if raw_index is not None else []
    )
    story_id_text = str(story_id)
    if story_id_text not in story_ids:
        story_ids.append(story_id_text)
        await store.put(key, json.dumps(story_ids))


def _story_key(story_id: UUID) -> str:
    return f"{_STORY_KEY_PREFIX}{story_id}"


def _device_stories_key(device_id: UUID) -> str:
    return f"{_DEVICE_STORIES_KEY_PREFIX}{device_id}"


def _cloudflare_kv_text(value: Any | None) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if text in {"", "None", "undefined", "null"}:
        return None

    return text


def _story_ids_from_index_payload(raw_index: str) -> list[str]:
    try:
        story_ids = json.loads(raw_index)
    except JSONDecodeError:
        return []

    if not isinstance(story_ids, list):
        return []

    return [str(story_id) for story_id in story_ids]
