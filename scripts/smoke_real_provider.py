#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4


OPT_IN_ENV = "REAL_PROVIDER_SMOKE"
BASE_URL_ENV = "SMOKE_BASE_URL"
TIMEOUT_SECONDS = 60


def main() -> int:
    if os.getenv(OPT_IN_ENV) != "1":
        print(
            "SKIPPED: set REAL_PROVIDER_SMOKE=1 to run the manual real-provider "
            "smoke check."
        )
        print(
            "This script calls only the configured backend public API and does "
            "not read provider secrets."
        )
        return 0

    base_url = os.getenv(BASE_URL_ENV, "http://127.0.0.1:8000").rstrip("/")
    device_id = os.getenv("SMOKE_DEVICE_ID", str(uuid4()))

    print(f"Running real-provider smoke check against {base_url}")
    print(
        "Prerequisite: start the backend with LLM_FAKE_MODE=false and real "
        "provider environment variables."
    )

    story = post_json(f"{base_url}/v1/stories", build_story_payload(device_id))
    story_id = require_string(story, "story_id")
    choices = require_list(story, "choices")
    if len(choices) != 3:
        print(f"FAILED: expected exactly 3 story choices, got {len(choices)}.")
        return 1

    flags = nested_dict(story, "current_state", "flags")
    if flags.get("fake_mode") is True:
        print(
            "FAILED: backend returned a fake-mode story. Start it with "
            "LLM_FAKE_MODE=false and real provider settings."
        )
        return 1
    if flags.get("story_opening_generated") is not True:
        print("FAILED: story state did not indicate provider-generated opening.")
        return 1

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        print("FAILED: first story choice is not an object.")
        return 1
    choice_id = require_string(first_choice, "id")

    print(
        "Story creation OK: "
        f"story_id={story_id}, choices={len(choices)}, "
        f"provider_opening={flags.get('story_opening_generated') is True}"
    )

    turn = post_json(
        f"{base_url}/v1/stories/{story_id}/turns",
        {
            "device_id": device_id,
            "input_type": "choice",
            "choice_id": choice_id,
            "user_text": None,
        },
    )
    turn_id = require_string(turn, "turn_id")
    turn_choices = require_list(turn, "choices")
    if len(turn_choices) != 3:
        print(f"FAILED: expected exactly 3 turn choices, got {len(turn_choices)}.")
        return 1
    usage = require_dict(turn, "usage")
    model = require_string(usage, "model")
    if model.startswith("fake-"):
        print(f"FAILED: turn used fake model metadata: {model}.")
        return 1

    turn_flags = nested_dict(turn, "state", "flags")
    if turn_flags.get("fake_provider_turn") is True:
        print("FAILED: turn state indicates the fake provider path was used.")
        return 1

    print(
        "Turn generation OK: "
        f"turn_id={turn_id}, choices={len(turn_choices)}, "
        f"model={model}, "
        f"input_tokens={usage.get('input_tokens')}, "
        f"output_tokens={usage.get('output_tokens')}, "
        f"warnings={len(turn.get('warnings') or [])}"
    )
    print("Smoke check completed without printing generated story text.")
    return 0


def build_story_payload(device_id: str) -> dict[str, Any]:
    return {
        "device_id": device_id,
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


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        print_http_error(exc)
        raise SystemExit(1) from exc
    except urllib.error.URLError as exc:
        print(f"FAILED: backend request failed before a response: {exc.reason}")
        raise SystemExit(1) from exc
    except TimeoutError as exc:
        print(f"FAILED: backend request timed out after {TIMEOUT_SECONDS}s.")
        raise SystemExit(1) from exc

    try:
        decoded = json.loads(response_body)
    except json.JSONDecodeError as exc:
        print("FAILED: backend returned non-JSON response.")
        raise SystemExit(1) from exc

    if not isinstance(decoded, dict):
        print("FAILED: backend response was not a JSON object.")
        raise SystemExit(1)

    return decoded


def print_http_error(exc: urllib.error.HTTPError) -> None:
    body = exc.read()
    summary = sanitized_error_summary(body)
    code = summary.get("code") or "unknown_error"
    reason = summary.get("reason")
    if reason:
        print(f"FAILED: backend returned HTTP {exc.code}: {code} ({reason}).")
        return

    print(f"FAILED: backend returned HTTP {exc.code}: {code}.")


def sanitized_error_summary(body: bytes) -> dict[str, str]:
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}

    if not isinstance(decoded, dict):
        return {}
    error = decoded.get("error")
    if not isinstance(error, dict):
        return {}

    details = error.get("details")
    reason = details.get("reason") if isinstance(details, dict) else None
    summary: dict[str, str] = {}
    if isinstance(error.get("code"), str):
        summary["code"] = error["code"]
    if isinstance(reason, str):
        summary["reason"] = reason
    return summary


def require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        print(f"FAILED: response field {key!r} is missing or not a string.")
        raise SystemExit(1)
    return value


def require_list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        print(f"FAILED: response field {key!r} is missing or not a list.")
        raise SystemExit(1)
    return value


def require_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        print(f"FAILED: response field {key!r} is missing or not an object.")
        raise SystemExit(1)
    return value


def nested_dict(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


if __name__ == "__main__":
    sys.exit(main())
