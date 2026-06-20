# AI Playable Novel MVP Development Spec

Version: 0.3
Target user: overseas Chinese readers first, English expansion later
Target platform: iOS MVP plus backend API
Product name: StoryCat / 故事猫
Brand signature: by Station Cat
App Store English title: StoryCat: AI Playable Novel
App Store Chinese title: StoryCat 故事猫
Original working title: Playable Novel

This document is written so Codex can implement the MVP in phases. The goal is to build a working TestFlight-ready prototype, not a design-only demo.

---

## 0. Codex Project Memory and Phase Control Protocol

This section is mandatory for all future development documents in this project. Codex must use repository files as persistent memory. Do not rely only on chat history.

### 0.1 Required memory files

Codex must create and maintain these files in the repository root:

```text
PROJECT_CONTEXT.md
CURRENT_PHASE.md
PHASE_LOG.md
DECISIONS.md
ARCHITECTURE.md
API_CONTRACT.md
TESTING_CHECKLIST.md
NEXT_TASKS.md
```

If any file is missing, Codex must create it from this spec before writing product code.

### 0.2 What each memory file must contain

`PROJECT_CONTEXT.md` must contain the stable product rules:

- Product: AI-generated playable novel for overseas Chinese users first.
- Future expansion: English market after the Chinese MVP has usage data.
- MVP scope: private AI interactive story generation.
- Avoid: existing novel import, copyrighted IP roleplay, public UGC sharing, China mainland launch, complex payment, multiplayer, creator marketplace.
- Architecture: SwiftUI iOS app, FastAPI backend, backend LLM gateway, fake mode first, Qwen or another OpenAI-compatible provider later.
- Development rule: phase-by-phase implementation with small goals and explicit acceptance gates.

`CURRENT_PHASE.md` must contain:

- current phase number and name
- phase goal
- exact scope
- explicit out-of-scope items
- tasks in progress
- acceptance criteria
- test commands
- blockers

`PHASE_LOG.md` must contain one entry after every completed phase:

- phase completed
- date
- files changed
- features delivered
- tests run
- acceptance status
- known issues
- next recommended phase

`DECISIONS.md` must contain product and engineering decisions that should not be lost:

- why fake mode comes before real LLM calls
- why LLM keys stay only on the backend
- why MVP excludes China mainland launch
- why public UGC is excluded from MVP
- why quota routing is required before large-scale testing
- any later architecture or product tradeoff

`ARCHITECTURE.md` must contain:

- backend modules
- iOS modules
- database schema summary
- LLM gateway design
- quota router design
- safety filter design

`API_CONTRACT.md` must contain:

- all routes
- request and response schemas
- example payloads
- error formats
- versioning notes

`TESTING_CHECKLIST.md` must contain:

- automated backend tests
- manual iOS checks
- fake mode checks
- LLM router quota tests
- end-to-end story creation and turn generation tests

`NEXT_TASKS.md` must contain:

- the next smallest task Codex should perform
- blocked tasks
- tasks explicitly deferred

### 0.3 Codex startup protocol for every session

At the start of every Codex session, Codex must do this before coding:

1. Read this spec.
2. Read all repository memory files listed in section 0.1.
3. Summarize the current phase in plain language.
4. Confirm the next smallest task.
5. Touch only the files needed for the current phase.
6. Run the relevant tests or write the missing tests first.
7. Update memory files after completing the task.

If Codex is asked to continue work and the current phase is unclear, it must inspect `CURRENT_PHASE.md`, `PHASE_LOG.md`, and `NEXT_TASKS.md` before changing code.

### 0.4 Phase control rule

Every development document must be organized by phases. Each phase must include:

- phase goal
- development scope
- explicit out-of-scope items
- deliverables
- acceptance criteria
- tests or manual checks
- Codex task prompt
- condition for entering the next phase

Codex must not start a later phase until the current phase acceptance checks pass or a human explicitly overrides the gate.

### 0.5 Scope control rule

Keep each phase small enough to finish and verify independently. Prefer one working loop over many half-built features.

Default sequence:

1. Project foundation.
2. Backend fake mode.
3. Core state engine.
4. Real LLM integration.
5. iOS MVP integration.
6. Playability polish.
7. Safety, compliance, and TestFlight preparation.
8. Closed beta metrics.
9. Post-MVP expansion decision.

### 0.6 Standard Codex continuation prompt

Use this prompt when starting a new Codex session:

```text
Before coding, read AI_Playable_Novel_MVP_Dev_Spec_Phased_v0_3.md and the repository memory files: PROJECT_CONTEXT.md, CURRENT_PHASE.md, PHASE_LOG.md, DECISIONS.md, ARCHITECTURE.md, API_CONTRACT.md, TESTING_CHECKLIST.md, and NEXT_TASKS.md.

Summarize the current phase, the previous completed phase, and the next smallest task. Then implement only the next task for the current phase. Do not skip phases. Do not add features outside the current phase. After coding, run the relevant tests and update the memory files.
```

---

## 1. Product Summary

Build an iOS app where a user chooses a story template, customizes a protagonist, and enters an AI-generated interactive novel. The app generates a structured long-form story plan, then lets the player advance chapter by chapter through choices and free-text actions.

The MVP must avoid importing third-party novels, avoid public UGC sharing, and avoid China mainland App Store launch. It should be a private AI interactive story tool for each user.

Core promise:

> Set a world, create a protagonist, and personally enter an AI-generated long-form novel.

MVP positioning:

> AI interactive story generator, focused on Chinese web-novel style pacing.

Do not position MVP as:

- third-party novel importer
- copyrighted IP roleplay
- public UGC story marketplace
- AI companion or AI lover app
- China mainland game product

---

## 2. MVP Goals

The MVP is successful if a tester can:

1. Open the app and select a story template.
2. Create a protagonist with name, gender/pronouns, personality, goal, and special ability.
3. Generate a story bible and chapter outline.
4. Play at least 30 turns in one story.
5. See story state persist across app restarts.
6. Use both preset choices and free-text actions.
7. See character relationships, inventory, current goal, and chapter progress update.
8. Send feedback on a generated turn.
9. Use the app without any LLM API key stored in the iOS client.

---

## 3. Non-Goals for MVP

Do not build these in the first version:

- importing existing novels
- scraping websites
- public story sharing
- multiplayer
- creator marketplace
- image generation
- voice generation
- China mainland App Store availability
- App Store subscription purchase flow, except a placeholder paywall screen
- Apple Foundation Models production path, except an optional future adapter interface
- full account system with email/password
- social feed, comments, likes, follows, leaderboards

---

## 4. Recommended Tech Stack

### 4.1 iOS App

Use:

- SwiftUI
- iOS 17+ minimum deployment target
- SwiftData for local persistence
- URLSession for API calls
- Keychain for anonymous device user ID
- No third-party iOS SDKs in MVP unless absolutely necessary

Reasoning:

- iOS 17+ gives SwiftData while keeping better device coverage than requiring iOS 26.
- Apple Foundation Models can be considered later for on-device helper tasks, but the MVP should rely on backend LLM calls to avoid device coverage constraints.

### 4.2 Backend

Use:

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy or SQLModel
- SQLite for local development
- PostgreSQL-ready database config for production
- Uvicorn
- Pytest
- OpenAI-compatible LLM client interface

### 4.3 LLM Provider

Implement a provider abstraction. Default provider should support Alibaba Cloud Model Studio Qwen through its OpenAI-compatible Chat Completions API.

Required environment variables:

```bash
LLM_PROVIDER=qwen
LLM_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=replace_me
LLM_MODEL_FAST=qwen-flash
LLM_MODEL_QUALITY=qwen-plus
LLM_TIMEOUT_SECONDS=60
LLM_FAKE_MODE=false

# Optional MVP quota router settings
LLM_ROUTER_ENABLED=true
LLM_DEFAULT_MONTHLY_TOKEN_BUDGET=1000000
LLM_DEFAULT_DAILY_TOKEN_BUDGET=100000
LLM_DEFAULT_MONTHLY_COST_BUDGET_USD=25
LLM_FALLBACK_FAST_MODELS=qwen-flash,qwen-turbo,qwen-plus
LLM_FALLBACK_QUALITY_MODELS=qwen-plus,qwen-max,qwen-flash
```

Allow replacing the model provider later without changing app code.

Important:

- Never put LLM keys in the iOS app.
- The iOS app calls only our backend.
- Support `LLM_FAKE_MODE=true` for deterministic local development and tests.

---

## 5. High-Level Architecture

```text
iOS App
  SwiftUI screens
  SwiftData local cache
  Keychain anonymous user ID
  APIClient using URLSession
        |
        v
Backend API, FastAPI
  Auth-lite device session
  Story service
  Turn service
  State manager
  Safety filter
  LLM gateway
        |
        v
LLM Provider
  Qwen OpenAI-compatible API
  future: OpenAI, Anthropic, Gemini, local model

Database
  users/devices
  story_templates
  stories
  turns
  llm_calls
  feedback
```

---

## 6. User Flow

### Flow A: New Story

1. User opens app.
2. App creates or loads an anonymous device ID from Keychain.
3. App calls `POST /v1/device-session`.
4. App shows home screen with story templates.
5. User picks a template.
6. User fills protagonist form:
   - name
   - gender/pronoun option
   - age range, no minors as romantic targets
   - personality trait
   - starting role
   - main goal
   - special ability
   - tone preference
7. App calls `POST /v1/stories`.
8. Backend generates story bible and chapter outline.
9. App opens play screen with first scene.

### Flow B: Play Turn

1. User selects a choice or enters a free-text action.
2. App calls `POST /v1/stories/{story_id}/turns`.
3. Backend validates quota and input safety.
4. Backend builds compact prompt from story state.
5. LLM returns strict JSON.
6. Backend validates JSON and applies `state_patch`.
7. Backend saves turn and updated story state.
8. App displays narrative and next choices.

### Flow C: Resume Story

1. User opens app.
2. App loads local story list from SwiftData.
3. App syncs latest server story state if online.
4. User continues from latest turn.

---

## 7. Story Templates for MVP

Implement at least 5 templates.

### Template 1: 修仙逆袭

- id: `xianxia_rise`
- genre: cultivation fantasy
- premise: A weak outsider enters a sect and uncovers a hidden fate.
- core loop: trial, cultivation, relationship, secret, breakthrough
- ending style: ascension or moral victory

### Template 2: 末世基地

- id: `apocalypse_base`
- genre: post-apocalypse survival
- premise: Civilization collapses and the protagonist must build a team and shelter.
- core loop: scavenge, recruit, defend, discover, decide
- ending style: safe haven or sacrifice

### Template 3: 都市异能

- id: `urban_ability`
- genre: urban superpower
- premise: An ordinary person awakens an ability and enters a hidden power struggle.
- core loop: investigate, train, conceal identity, fight, reveal truth
- ending style: public revelation or hidden guardian

### Template 4: 无限试炼

- id: `infinity_trial`
- genre: survival trial / portal worlds
- premise: The protagonist is pulled into dangerous scenario worlds with hidden rules.
- core loop: understand rules, form alliances, survive, solve twist
- ending style: escape or become rule-maker

### Template 5: 悬疑探案

- id: `detective_mystery`
- genre: detective mystery
- premise: A strange case reveals a larger conspiracy.
- core loop: clue, suspect, contradiction, risk, reveal
- ending style: solve truth, expose conspiracy

Optional sixth template:

### Template 6: 权谋上位

- id: `palace_strategy`
- genre: palace / political strategy
- premise: A low-status protagonist survives factional conflict.
- core loop: alliance, information, betrayal, leverage, reversal
- ending style: reform power or escape power

---

## 8. Core Game State

Every story has a canonical state object stored on the backend.

```json
{
  "story_id": "uuid",
  "locale": "zh-Hans",
  "template_id": "xianxia_rise",
  "title": "string",
  "protagonist": {
    "name": "string",
    "pronouns": "string",
    "age_band": "adult",
    "personality": ["calm", "ambitious"],
    "starting_role": "outer disciple",
    "main_goal": "avenge family and find lost sibling",
    "special_ability": "can sense unstable spiritual energy"
  },
  "story_bible": {
    "world_rules": ["string"],
    "tone": "string",
    "forbidden_moves": ["string"],
    "major_factions": [
      {"name": "string", "goal": "string", "attitude": "string"}
    ],
    "main_characters": [
      {
        "id": "npc_001",
        "name": "string",
        "role": "string",
        "personality": "string",
        "secret": "string",
        "relationship_to_player": "string"
      }
    ]
  },
  "plot_plan": {
    "total_chapters": 8,
    "chapters": [
      {
        "index": 1,
        "title": "string",
        "goal": "string",
        "required_outcome": "string",
        "possible_branches": ["string"],
        "cliffhanger": "string"
      }
    ]
  },
  "current_chapter_index": 1,
  "current_scene_index": 1,
  "active_goal": "string",
  "short_summary": "string",
  "long_summary": "string",
  "relationships": {
    "npc_001": {"affinity": 10, "trust": 5, "status": "neutral"}
  },
  "inventory": [
    {"id": "item_001", "name": "string", "description": "string"}
  ],
  "stats": {
    "danger": 10,
    "reputation": 0,
    "power": 1,
    "health": 100
  },
  "flags": {
    "met_mentor": true,
    "knows_hidden_enemy": false
  },
  "turn_count": 0,
  "updated_at": "iso_datetime"
}
```

---

## 9. Backend API Contract

Base path: `/v1`

### 9.1 Health

`GET /health`

Response:

```json
{"status": "ok"}
```

### 9.2 Device Session

`POST /v1/device-session`

Request:

```json
{
  "device_id": "uuid_from_keychain",
  "app_version": "0.1.0",
  "locale": "zh-Hans"
}
```

Response:

```json
{
  "user_id": "uuid",
  "device_id": "uuid",
  "daily_turn_limit": 50,
  "turns_used_today": 0
}
```

MVP auth is intentionally lightweight. Use a device-generated UUID. Add Sign in with Apple later.

### 9.3 List Templates

`GET /v1/templates?locale=zh-Hans`

Response:

```json
{
  "templates": [
    {
      "id": "xianxia_rise",
      "name": "修仙逆袭",
      "genre": "修仙",
      "short_description": "从边缘小人物开始，踏入宗门、秘境和天命之争。",
      "tags": ["升级", "宗门", "秘境", "爽文"],
      "recommended_tone": ["热血", "暗线", "成长"]
    }
  ]
}
```

### 9.4 Create Story

`POST /v1/stories`

Request:

```json
{
  "device_id": "uuid",
  "template_id": "xianxia_rise",
  "locale": "zh-Hans",
  "protagonist": {
    "name": "林澈",
    "pronouns": "他",
    "age_band": "adult",
    "personality": ["冷静", "不服输"],
    "starting_role": "被宗门轻视的外门弟子",
    "main_goal": "查清家族没落真相",
    "special_ability": "能听见灵气裂隙中的低语"
  },
  "tone": "热血、悬念、成长",
  "content_rating": "teen"
}
```

Response:

```json
{
  "story_id": "uuid",
  "title": "裂隙听灵者",
  "opening_narrative": "string",
  "current_state": {},
  "choices": [
    {"id": "choice_1", "label": "低头忍耐，先观察局势", "risk": "low"},
    {"id": "choice_2", "label": "当众反击，争取试炼机会", "risk": "medium"},
    {"id": "choice_3", "label": "私下寻找掌事长老", "risk": "medium"}
  ]
}
```

### 9.5 Get Story

`GET /v1/stories/{story_id}`

Response:

```json
{
  "story_id": "uuid",
  "title": "string",
  "current_state": {},
  "latest_turns": []
}
```

### 9.6 List Stories

`GET /v1/stories?device_id=uuid`

Response:

```json
{
  "stories": [
    {
      "story_id": "uuid",
      "title": "string",
      "template_id": "xianxia_rise",
      "current_chapter_index": 1,
      "turn_count": 12,
      "updated_at": "iso_datetime"
    }
  ]
}
```

### 9.7 Play Turn

`POST /v1/stories/{story_id}/turns`

Request:

```json
{
  "device_id": "uuid",
  "input_type": "choice",
  "choice_id": "choice_2",
  "user_text": null
}
```

Free-text request:

```json
{
  "device_id": "uuid",
  "input_type": "free_text",
  "choice_id": null,
  "user_text": "我假装认输，但偷偷观察谁在笑得最得意。"
}
```

Response:

```json
{
  "turn_id": "uuid",
  "story_id": "uuid",
  "narrative": "string",
  "choices": [
    {"id": "choice_1", "label": "string", "risk": "low"},
    {"id": "choice_2", "label": "string", "risk": "medium"},
    {"id": "choice_3", "label": "string", "risk": "high"}
  ],
  "state": {},
  "chapter_progress": {
    "current_chapter_index": 1,
    "current_scene_index": 2,
    "progress_percent": 22
  },
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "model": "qwen-flash"
  },
  "warnings": []
}
```

### 9.8 Feedback

`POST /v1/feedback`

Request:

```json
{
  "device_id": "uuid",
  "story_id": "uuid",
  "turn_id": "uuid",
  "rating": "thumbs_down",
  "reason": "人物突然变得不像自己",
  "free_text": "这一段太快了，希望多一点对话。"
}
```

Response:

```json
{"status": "ok"}
```

---

## 10. LLM Call Design

### 10.1 Model Tiers

Use two model tiers:

- Fast model: normal turns, summaries, state extraction
- Quality model: story bible, chapter outline, major chapter transition, ending generation

MVP default:

```text
fast: qwen-flash
quality: qwen-plus
```

### 10.2 Token Budget Targets

For each normal turn:

- input target: 3,000 to 6,000 tokens
- output target: 500 to 900 tokens
- choices: exactly 3 choices
- narrative: 250 to 650 Chinese characters for normal turns
- key chapter events may output 800 to 1,200 Chinese characters

Do not send full history every turn. Send:

- story bible compact version
- current chapter plan
- short summary
- latest 4 to 6 turns
- current state JSON
- player action

### 10.3 LLM Output Must Be Strict JSON

For turn generation, LLM must return only this JSON shape:

```json
{
  "narrative": "string",
  "choices": [
    {"id": "choice_1", "label": "string", "risk": "low"},
    {"id": "choice_2", "label": "string", "risk": "medium"},
    {"id": "choice_3", "label": "string", "risk": "high"}
  ],
  "state_patch": {
    "active_goal": "string or null",
    "short_summary_append": "string",
    "relationships": {
      "npc_id": {"affinity_delta": 0, "trust_delta": 0, "status": "string or null"}
    },
    "inventory_add": [],
    "inventory_remove_ids": [],
    "stats_delta": {
      "danger": 0,
      "reputation": 0,
      "power": 0,
      "health": 0
    },
    "flags_set": {
      "flag_name": true
    },
    "chapter_progress_delta": 1
  },
  "memory_update": {
    "new_facts": ["string"],
    "open_threads": ["string"],
    "resolved_threads": ["string"]
  },
  "safety": {
    "safe": true,
    "reason": "string"
  }
}
```

Backend must validate the JSON. If invalid:

1. Retry once with a repair prompt.
2. If still invalid, return a graceful fallback narrative and choices.
3. Log the failure in `llm_calls`.

### 10.4 Story Bible Generation Output

LLM must generate:

```json
{
  "title": "string",
  "opening_narrative": "string",
  "story_bible": {
    "world_rules": ["string"],
    "tone": "string",
    "forbidden_moves": ["string"],
    "major_factions": [],
    "main_characters": []
  },
  "plot_plan": {
    "total_chapters": 8,
    "chapters": []
  },
  "initial_state_patch": {},
  "choices": []
}
```

### 10.5 Model Router, Token Quotas, and Automatic Fallback

Implement an LLM router in Phase 3. The router decides which model to call for each task based on task type, configured priority, remaining budget, model health, and fallback rules.

The router must support these task types:

```text
story_bible_generation
chapter_outline_generation
normal_turn_generation
state_extraction
summary_generation
json_repair
safety_classification
ending_generation
```

Each task type maps to a model tier:

```text
fast: normal turns, summaries, state extraction, JSON repair, safety classification
quality: story bible, chapter outline, major chapter transition, ending generation
```

Quota policy:

- Each model can have a monthly token budget.
- Each model can have a daily token budget.
- Each model can have a monthly cost budget.
- Each user can have a daily turn limit.
- Each user can have a monthly token budget.
- Each story can have a soft monthly token budget.
- Each request must have a max input token target and max output token cap.

Example policy:

```json
{
  "tier": "fast",
  "primary_models": ["qwen-flash", "qwen-turbo", "qwen-plus"],
  "monthly_token_budget": 1000000,
  "daily_token_budget": 100000,
  "monthly_cost_budget_usd": 25,
  "max_output_tokens": 900,
  "fallback_when": [
    "budget_exhausted",
    "rate_limited",
    "provider_error",
    "timeout",
    "invalid_json_after_repair"
  ]
}
```

Important distinction:

- Context window limit controls how many tokens one request can hold.
- Budget limit controls how many tokens the app is willing to spend over time.
- A model can have a large context window but still be blocked by the app's budget policy.

Router behavior:

1. Estimate input tokens before making a call.
2. Reject or compress prompts that exceed the per-request input target.
3. Check model-level, user-level, and story-level budgets.
4. Pick the first healthy model with enough remaining budget.
5. Call the provider.
6. Read actual token usage from provider response if available.
7. Save actual usage to the usage ledger.
8. If the provider does not return usage, save estimated usage and mark it as estimated.
9. If the call fails due to rate limit, timeout, provider error, exhausted configured budget, or invalid JSON after repair, try the next configured fallback model.
10. If every model fails or every budget is exhausted, return a graceful app-level response.

Do not silently downgrade important story tasks too aggressively. For `story_bible_generation`, `chapter_outline_generation`, and `ending_generation`, prefer waiting for a quality model or showing a user-facing quota message over using a very weak model that may damage the story.

For normal turns, automatic fallback is acceptable because the structured story state can preserve continuity.

Database additions:

```text
llm_model_configs
  id
  provider
  model_name
  tier
  priority
  enabled
  monthly_token_budget
  daily_token_budget
  monthly_cost_budget_usd
  max_output_tokens
  notes
  created_at
  updated_at

llm_usage_ledger
  id
  user_id
  story_id nullable
  turn_id nullable
  task_type
  provider
  model_name
  input_tokens
  output_tokens
  total_tokens
  estimated boolean
  cost_usd nullable
  latency_ms
  status
  error_code nullable
  created_at

llm_model_health
  id
  provider
  model_name
  consecutive_failures
  last_success_at nullable
  last_failure_at nullable
  disabled_until nullable
  updated_at
```

Router interface:

```python
class LLMRouter(Protocol):
    async def complete(
        self,
        task_type: str,
        messages: list[dict],
        response_schema: type[BaseModel] | None,
        user_id: str,
        story_id: str | None = None,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        ...
```

`LLMResult` must include:

```python
class LLMResult(BaseModel):
    provider: str
    model: str
    content: str
    parsed_json: dict | None = None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    token_usage_estimated: bool
    latency_ms: int
    fallback_used: bool
    fallback_chain: list[str]
    finish_reason: str | None = None
```

Implementation notes:

- The iOS client must never choose the provider model directly in MVP.
- The backend may expose a simple quality setting later, such as `standard` or `premium`, but Phase 3 should keep model routing server-side only.
- Store the model used for each turn so debugging is possible.
- If a fallback model is used, the response should still follow the same JSON schema.
- Keep style stable by always sending the same story bible, tone instructions, and state JSON regardless of selected model.
- Add unit tests for budget exhaustion and fallback order.

Acceptance criteria for quota router:

- A model with exhausted monthly budget is skipped.
- A model with exhausted daily budget is skipped.
- A disabled or unhealthy model is skipped until its cooldown expires.
- If the primary fast model is exhausted, the next fast fallback model is used.
- If all models in a tier are exhausted, the API returns a clear quota error.
- Usage is logged for every fake and real model call.
- Tests can simulate 1,000,000 token usage and verify automatic fallback.

---

## 11. Prompt Templates

Create backend files:

```text
server/app/prompts/story_creator_zh.md
server/app/prompts/turn_director_zh.md
server/app/prompts/json_repair_zh.md
server/app/prompts/safety_classifier_zh.md
```

### 11.1 Story Creator Prompt

```text
You are the story architect for an AI interactive novel app.
Language: Simplified Chinese unless the locale requests otherwise.

Create an original interactive novel. Do not use existing copyrighted characters, worlds, plots, brands, or named IP. The user wants a genre-inspired original story.

The story must be structured enough for a game:
- 8 chapters
- each chapter has a clear goal
- each chapter has a required outcome
- each chapter allows flexible player choices
- final ending should feel earned

Keep content teen-safe. No explicit sexual content. No sexual minors. No real-person imitation. No instructions for real-world crime, self-harm, or violence.

Return only valid JSON matching the required schema.
```

### 11.2 Turn Director Prompt

```text
You are the game master and narrative director for a private AI interactive novel.
Language: Simplified Chinese unless the story locale requests otherwise.

Your job:
1. Continue the current scene based on player action.
2. Respect the story bible, character sheets, world rules, and current chapter goal.
3. Let the player feel agency, but keep the story moving toward the chapter required outcome.
4. Do not resolve major conflicts too early.
5. Do not randomly kill major NPCs.
6. Do not grant huge power jumps unless the plot plan supports it.
7. Do not mention that you are an AI model.
8. Do not copy existing copyrighted IP.
9. Keep content teen-safe.
10. Return only strict JSON.

Writing style:
- vivid but concise
- Chinese web-novel pacing
- clear stakes
- end with meaningful choices
- avoid walls of text
- avoid repetitive openings

For every turn, produce:
- narrative
- exactly 3 choices
- state_patch
- memory_update
- safety
```

### 11.3 JSON Repair Prompt

```text
The previous model output was invalid JSON.
Repair it to match the required schema.
Do not add commentary.
Return only valid JSON.
```

---

## 12. Safety and Compliance Requirements

MVP must include basic safety even without public sharing.

### 12.1 Input Rules

Reject or redirect if user asks for:

- explicit sexual content
- sexual content involving minors
- real-person sexual or romantic roleplay
- instructions for real-world crime
- self-harm encouragement
- hateful or extremist content
- direct use of copyrighted IP, such as asking to enter a named existing franchise world

### 12.2 Copyright/IP Rules

If the user enters an existing work or famous IP name, the app should redirect:

> 这个设定可能涉及已有作品或角色。我可以为你生成一个同类型、原创世界的故事。

### 12.3 App Store Strategy

MVP should have:

- no public UGC feed
- no anonymous random chat
- report issue button for every generated turn
- feedback email in settings
- clear AI-generated content notice
- terms and privacy placeholder screens
- App Store availability configured to selected overseas regions only

Suggested first availability regions:

- United States
- Canada
- United Kingdom
- Australia
- New Zealand
- Singapore
- Malaysia
- Japan
- Hong Kong
- Taiwan
- Macau

Do not include Mainland China availability in MVP.

---

## 13. Database Schema

Use SQLModel or SQLAlchemy. SQLite local dev is acceptable. Schema should be PostgreSQL-compatible.

### users

```text
id UUID primary key
device_id string unique indexed
locale string
created_at datetime
updated_at datetime
```

### story_templates

```text
id string primary key
locale string
name string
genre string
short_description text
definition_json json
created_at datetime
updated_at datetime
```

Templates can also be loaded from static JSON files in MVP.

### stories

```text
id UUID primary key
user_id UUID indexed
template_id string
title string
locale string
state_json json
status string
turn_count int
created_at datetime
updated_at datetime
```

Status values:

```text
active
completed
archived
error
```

### turns

```text
id UUID primary key
story_id UUID indexed
user_id UUID indexed
input_type string
choice_id string nullable
user_text text nullable
narrative text
choices_json json
state_patch_json json
memory_update_json json
created_at datetime
```

### llm_calls

```text
id UUID primary key
story_id UUID nullable
turn_id UUID nullable
provider string
model string
purpose string
input_tokens int nullable
output_tokens int nullable
latency_ms int nullable
success bool
error text nullable
created_at datetime
```

Purpose values:

```text
story_create
turn_generate
json_repair
summary
safety
```

### feedback

```text
id UUID primary key
user_id UUID indexed
story_id UUID indexed
turn_id UUID nullable
rating string
reason text nullable
free_text text nullable
created_at datetime
```

---

## 14. iOS Screens

### 14.1 HomeView

Purpose:

- show app title
- show resume story cards
- show create new story button
- show settings button

### 14.2 TemplateSelectionView

Purpose:

- list templates
- show tags and descriptions
- choose template

### 14.3 ProtagonistSetupView

Fields:

- name
- pronoun option
- personality chips
- starting role
- main goal
- special ability
- tone chips

CTA:

- Generate Story

Validation:

- name is required
- no famous IP or real-person names if detectable
- adult or non-age-specific protagonist only

### 14.4 StoryLoadingView

Purpose:

- show generation progress
- allow cancel
- explain that the first generation creates the story bible

### 14.5 PlayView

Main sections:

- chapter title and progress
- narrative card
- three choice buttons
- free-text action input
- send button
- side panel or sheet for state

State sheet:

- current goal
- protagonist stats
- relationships
- inventory
- unresolved threads

### 14.6 StoryListView

Purpose:

- all saved stories
- title, template, chapter, turn count, updated time
- continue or archive

### 14.7 SettingsView

MVP items:

- app version
- model mode label
- AI-generated content notice
- privacy policy placeholder
- terms placeholder
- feedback email placeholder

### 14.8 FeedbackView

Available from PlayView on each turn:

- thumbs up
- thumbs down
- reason chips
- text comment

---

## 15. iOS Local Persistence

Use SwiftData for local cache.

Local models:

```swift
@Model final class LocalStory {
    @Attribute(.unique) var storyID: String
    var title: String
    var templateID: String
    var locale: String
    var currentChapterIndex: Int
    var turnCount: Int
    var updatedAt: Date
    var stateJSON: String
}

@Model final class LocalTurn {
    @Attribute(.unique) var turnID: String
    var storyID: String
    var narrative: String
    var choicesJSON: String
    var createdAt: Date
}
```

Keychain:

```text
key: playable_novel_device_id
value: UUID string
```

---

## 16. Backend Project Structure

Create this repository layout:

```text
playable-novel/
  README.md
  .gitignore
  server/
    README.md
    pyproject.toml
    .env.example
    app/
      __init__.py
      main.py
      config.py
      database.py
      models.py
      schemas.py
      api/
        __init__.py
        routes_health.py
        routes_sessions.py
        routes_templates.py
        routes_stories.py
        routes_feedback.py
      services/
        __init__.py
        story_service.py
        turn_service.py
        state_manager.py
        safety_service.py
        quota_service.py
        llm/
          __init__.py
          base.py
          qwen_provider.py
          fake_provider.py
          json_utils.py
      prompts/
        story_creator_zh.md
        turn_director_zh.md
        json_repair_zh.md
        safety_classifier_zh.md
      templates/
        zh-Hans.json
      tests/
        test_health.py
        test_templates.py
        test_story_create_fake.py
        test_turn_fake.py
        test_state_manager.py
  ios/
    PlayableNovel/
      PlayableNovel.xcodeproj
      PlayableNovel/
        PlayableNovelApp.swift
        AppConfig.swift
        Models/
        Services/
        Views/
        Persistence/
        Resources/
```

If Codex cannot create a reliable Xcode project in the current environment, it should still create all Swift source files under the intended structure and include clear Xcode setup instructions in `ios/README.md`.

---

## 17. Backend Implementation Details

### 17.1 Configuration

`config.py` should load:

```text
DATABASE_URL
LLM_PROVIDER
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL_FAST
LLM_MODEL_QUALITY
LLM_TIMEOUT_SECONDS
LLM_FAKE_MODE
DAILY_TURN_LIMIT
```

### 17.2 LLM Provider Interface

```python
class LLMProvider(Protocol):
    async def chat_json(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        purpose: str,
    ) -> LLMResult: ...
```

`LLMResult`:

```python
class LLMResult(BaseModel):
    content: str
    parsed_json: dict | None = None
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    success: bool
    error: str | None = None
```

### 17.3 Fake Provider

`fake_provider.py` must produce deterministic responses for:

- story creation
- turn generation
- JSON repair

This is required for tests and UI development without paid API calls.

### 17.4 State Manager

`state_manager.py` applies a validated state patch to story state.

Rules:

- clamp stats to safe ranges
- affinity/trust range: -100 to 100
- danger range: 0 to 100
- health range: 0 to 100
- power should not jump more than +1 in a normal turn
- chapter progress should not exceed chapter boundaries
- unknown inventory remove IDs should be ignored
- flags can be added or updated

### 17.5 Quota Service

MVP quota:

- default `DAILY_TURN_LIMIT=50`
- count by user_id and date
- story creation counts as 3 turns internally or separate generation quota

Return HTTP 429 if quota exceeded.

---

## 18. Error Handling

Backend should return friendly errors:

### LLM unavailable

```json
{
  "error": "llm_unavailable",
  "message": "故事引擎暂时无法响应，请稍后再试。"
}
```

### Unsafe input

```json
{
  "error": "unsafe_input",
  "message": "这个行动不适合当前故事。我可以帮你换成一个原创且安全的选择。"
}
```

### Quota exceeded

```json
{
  "error": "quota_exceeded",
  "message": "今天的免费回合数已用完。"
}
```

### Invalid story state

```json
{
  "error": "invalid_story_state",
  "message": "这个存档出现异常，请返回故事列表重试。"
}
```

---

## 19. Testing Requirements

### Backend Tests

Required tests:

1. `GET /health` returns ok.
2. `GET /v1/templates` returns at least 5 templates.
3. `POST /v1/device-session` creates or returns a user.
4. `POST /v1/stories` works in fake mode.
5. `POST /v1/stories/{id}/turns` works in fake mode.
6. State patch clamps stats correctly.
7. Unsafe input returns safe response.
8. Quota service blocks after daily limit.
9. JSON repair fallback works.
10. LLM API key is never exposed in API responses.

### iOS Tests

Minimum:

1. APIClient decodes templates.
2. APIClient decodes story creation response.
3. APIClient decodes turn response.
4. Device ID persists across launches.
5. LocalStory saves and loads.

### Manual Test Script

1. Start backend in fake mode.
2. Launch app.
3. Create a `修仙逆袭` story.
4. Play 5 preset-choice turns.
5. Play 2 free-text turns.
6. Kill and reopen the app.
7. Resume story.
8. Submit feedback.
9. Confirm feedback row exists in database.

---

## 20. Analytics Events for MVP

No third-party analytics required. Log server-side events only.

Event names:

```text
session_started
template_selected
story_created
turn_generated
free_text_turn_generated
choice_turn_generated
feedback_submitted
quota_exceeded
llm_error
unsafe_input_detected
```

Store event logs if easy, or print structured logs in MVP.

---

## 21. AI Content Notice

Settings and story creation screen should show:

```text
本应用会根据你的设定生成原创互动故事。生成内容可能出现不准确、重复或不符合预期的情况。请不要输入他人受版权保护的作品、现实个人隐私信息或违法内容。
```

For future English localization:

```text
This app generates original interactive stories from your settings. AI-generated content may be inaccurate, repetitive, or unexpected. Do not enter copyrighted works, private personal information, or illegal content.
```

---

## 22. Localization Plan

MVP:

- `zh-Hans` first
- prepare string keys for `zh-Hant` and `en`, but do not require full translation before MVP

String key examples:

```text
app.title
home.create_story
template.xianxia_rise.name
story.create.button
play.free_text.placeholder
settings.ai_notice.title
settings.ai_notice.body
error.llm_unavailable
error.quota_exceeded
```

---

## 23. Future Apple On-Device Model Integration

Do not implement this in MVP unless time remains.

Create only an interface placeholder:

```swift
protocol LocalAIHelper {
    func summarizeRecentTurns(_ turns: [LocalTurn]) async throws -> String
    func suggestChoices(context: String) async throws -> [String]
    func classifyUserIntent(_ text: String) async throws -> PlayerIntent
}
```

Future use cases:

- summarize recent turns
- classify player intent
- generate lightweight choices
- style rewrite
- local offline mode

The backend must remain the source of truth for story state.

---

## 24. Payment Strategy Placeholder

MVP should not implement paid subscriptions unless specifically requested.

Add a placeholder `PaywallView` only if quota exceeded:

```text
高级版即将开放：更多每日回合、更长记忆、更高质量模型和更多故事模板。
```

Future subscriptions:

- Free: limited daily turns
- Plus: more turns and longer memory
- Pro: quality model, longer chapters, more story slots

---


## 25. MVP Phase Roadmap

This project should be implemented in phases. Codex should complete one phase, run tests, and report what changed before moving to the next phase.

### Phase 0: Repository and development foundation

Goal:

Create a clean project foundation that can be developed safely without exposing any LLM keys in the iOS app.

Deliverables:

- Backend folder with FastAPI scaffold.
- iOS folder with SwiftUI app scaffold.
- Shared API contract notes or generated client models if desired.
- `.env.example` for backend configuration.
- `README.md` with local setup instructions.
- Fake LLM mode enabled by default.
- Basic backend test setup.

Acceptance criteria:

- Backend starts locally.
- `/health` returns a valid response.
- Tests can be run locally.
- No real LLM key is needed for this phase.
- No LLM key is present in the iOS project.

Do not implement yet:

- Real Qwen API calls.
- Payment.
- Public sharing.
- App Store metadata.

### Phase 1: Backend core API in fake mode

Goal:

Make the backend capable of creating and playing a fake interactive story end-to-end.

Deliverables:

- Device session endpoint.
- Template list endpoint.
- Create story endpoint.
- Get story endpoint.
- List stories endpoint.
- Play turn endpoint.
- Feedback endpoint.
- In-memory or SQLite-backed persistence for local development.

Acceptance criteria:

- A user can create a device session.
- A user can list story templates.
- A user can create a story using a template and protagonist profile.
- A user can play at least 5 fake turns.
- Story state updates after every turn.
- Story can be resumed after fetching it by ID.
- Backend tests cover the happy path and basic error paths.

Do not implement yet:

- Real model provider.
- Sophisticated safety filtering.
- iOS UI polish.

### Phase 2: Game state engine and story structure

Goal:

Stabilize the internal game state so the product behaves like a structured interactive novel, not a loose chatbot.

Deliverables:

- `StoryState` schema.
- `CharacterState` schema.
- `QuestState` or `CurrentObjective` schema.
- Inventory and relationship state.
- Chapter progress tracking.
- State manager service.
- Turn result validation.
- Rules for allowed and disallowed player actions.

Acceptance criteria:

- Every turn produces valid structured state.
- Player choices affect relationship, danger, inventory, or chapter progress.
- State cannot contain malformed JSON.
- The system can reject unsafe or impossible actions with a story-friendly redirect.
- At least one template can reach a chapter-complete state.

Do not implement yet:

- Long-term memory vector search.
- Complex combat simulation.
- Multiplayer.

### Phase 3: Real LLM provider integration

Goal:

Connect the backend to a real model provider while keeping fake mode available for tests.

Recommended first provider:

Qwen through Alibaba Cloud Model Studio or another OpenAI-compatible endpoint.

Deliverables:

- LLM provider interface.
- Fake provider implementation.
- Qwen/OpenAI-compatible provider implementation.
- Strict JSON response parsing.
- JSON repair retry path.
- LLM call logging table.
- Token and latency logging.
- Model router with per-model quota policy.
- Daily and monthly token budget checks.
- Automatic fallback chain for exhausted, unhealthy, or rate-limited models.
- Basic user-level and story-level quota control.

Acceptance criteria:

- Backend works in fake mode without external API access.
- Backend works with real provider when environment variables are configured.
- Invalid model JSON does not crash the app.
- Story creation and turn generation both work with the real provider.
- LLM API keys only exist in backend environment variables.
- When one model reaches its configured token budget, the router automatically uses the next allowed fallback model.
- Every model call records provider, model, task type, input tokens, output tokens, status, latency, and whether fallback was used.

Do not implement yet:

- Multiple paid model tiers.
- User-facing model selection.
- Self-hosted model deployment.

### Phase 4: iOS MVP app flow

Goal:

Build the minimum iOS app that can create, play, and resume stories.

Deliverables:

- Home screen.
- Template selection screen.
- Protagonist setup screen.
- Story loading screen.
- Play screen.
- Story list screen.
- Settings screen.
- Feedback screen.
- Local device ID persistence.
- Local story cache.

Acceptance criteria:

- App builds in Xcode.
- User can create a story from the app.
- User can select a suggested choice.
- User can submit free-text action.
- User can resume a previous story after app restart.
- App handles loading, quota, unsafe input, and backend error states gracefully.

Do not implement yet:

- Beautiful visual design.
- In-app purchase.
- Public story discovery.
- Creator marketplace.

### Phase 5: End-to-end playable MVP polish

Goal:

Make the first version feel like a playable product instead of a technical demo.

Deliverables:

- At least 5 strong templates.
- Better opening scene quality.
- Better suggested choices.
- Basic chapter progress indicator.
- Basic relationship and inventory display.
- AI content notice.
- Feedback collection.
- Manual QA script.

Acceptance criteria:

- A tester can play from story creation through at least 20 turns without developer assistance.
- Narrative remains coherent across 20 turns.
- Choices feel meaningfully different.
- State changes are visible to the player.
- Feedback can be submitted from inside the app.

Do not implement yet:

- Full-length 100-chapter stories.
- Advanced memory retrieval.
- Public UGC.

### Phase 6: Safety, compliance, and TestFlight readiness

Goal:

Prepare the app for small external testing while reducing obvious App Store and user safety risks.

Deliverables:

- Terms placeholder screen or link.
- Privacy placeholder screen or link.
- AI content disclosure.
- Basic IP/copyright input warning.
- Basic content safety checks.
- Report/feedback contact route.
- TestFlight build checklist.
- App Store availability plan that excludes Mainland China for the MVP.

Acceptance criteria:

- App can be distributed to a small TestFlight group.
- No third-party novel import exists.
- No public sharing exists.
- No Mainland China-specific launch path is included.
- Users are clearly told that the story is AI-generated or AI-assisted.

Do not implement yet:

- Full legal compliance automation.
- Creator revenue share.
- Public moderation queue.

### Phase 7: Closed beta measurement

Goal:

Use a small group of testers to decide whether the product is fun enough to continue.

Deliverables:

- Simple analytics events.
- Feedback review workflow.
- Cost tracking per story and per turn.
- Bug list.
- Product iteration notes.

Suggested metrics:

- Story creation completion rate.
- Average turns per story.
- D1 retention.
- D7 retention.
- Percentage of users who use free-text input.
- Cost per 100 turns.
- Feedback sentiment.

Acceptance criteria:

- At least 20 external testers complete story creation.
- At least 10 testers play 20 or more turns.
- Model cost per active tester is understood.
- Top 10 UX and story quality issues are documented.

Do not implement yet:

- Broad App Store launch.
- English expansion.
- Paid subscription.

### Phase 8: Post-MVP expansion decision

Goal:

Decide the next product direction based on real usage data.

Possible paths:

- English version with fantasy, mystery, romance, and post-apocalyptic templates.
- Subscription and premium model tier.
- Better long-term memory.
- More templates.
- Creator tools for private template creation.
- Apple on-device model support for lightweight tasks.

Decision criteria:

- Users voluntarily return to continue stories.
- Story generation cost is low enough for a paid plan.
- Testers ask for more templates or longer stories.
- The core gameplay loop is fun without needing public UGC.


## 26. Codex Implementation Tasks

Give Codex tasks in this order.

### Task 1: Backend scaffold

Create FastAPI server with config, health route, database setup, models, schemas, and tests.

Acceptance:

- `pytest` passes
- `uvicorn app.main:app --reload` starts
- `/health` returns ok

### Task 2: Templates and session API

Implement template loading from `server/app/templates/zh-Hans.json` and device session route.

Acceptance:

- returns at least 5 templates
- creates user by device ID
- repeated same device ID returns same user

### Task 3: LLM provider abstraction

Implement fake provider and Qwen OpenAI-compatible provider.

Acceptance:

- fake mode works without API key
- qwen provider reads env vars
- provider logs usage and latency
- provider never exposes API key

### Task 4: Story creation

Implement story creation service using quality model or fake provider.

Acceptance:

- creates story state
- saves story row
- saves opening as first turn or initial response
- returns title, opening narrative, state, and choices

### Task 5: Turn generation

Implement turn API with state manager, safety checks, quota, LLM call, JSON validation, retry repair, save turn.

Acceptance:

- choice turn works
- free-text turn works
- state updates
- invalid JSON fallback works in tests

### Task 6: iOS source files

Create SwiftUI app with Home, TemplateSelection, ProtagonistSetup, Loading, Play, StoryList, Settings, Feedback screens.

Acceptance:

- app builds in Xcode
- fake backend integration works
- local device ID persists
- local story cache persists

### Task 7: Integration polish

Connect app to backend API.

Acceptance:

- user can create and play a story end-to-end
- loading and error states are friendly
- feedback route works
- resume story works after app restart

### Task 8: TestFlight readiness checklist

Add README instructions, environment examples, manual test script, and App Store notes.

Acceptance:

- developer can run backend locally
- developer can configure app API base URL
- manual test script passes

---

## 27. Master Prompt to Give Codex

Paste this to Codex with this document:

```text
You are implementing the MVP described in AI_Playable_Novel_MVP_Dev_Spec_Phased_v0_3.md.

Before coding, read this spec and the repository memory files: PROJECT_CONTEXT.md, CURRENT_PHASE.md, PHASE_LOG.md, DECISIONS.md, ARCHITECTURE.md, API_CONTRACT.md, TESTING_CHECKLIST.md, and NEXT_TASKS.md.

If the memory files do not exist, create them from section 0 of this spec before writing product code. Use them as persistent project memory. At the end of every task, update CURRENT_PHASE.md, PHASE_LOG.md, DECISIONS.md, and NEXT_TASKS.md as needed.

Build a working iOS + backend prototype. Prioritize correctness, clean architecture, and testability over visual polish.

Hard requirements:
- Do not store any LLM API key in the iOS app.
- Use backend LLM gateway with a fake mode for local tests.
- Use FastAPI, Pydantic v2, Python 3.12+ for backend.
- Use SwiftUI and SwiftData for iOS.
- Implement the API contract in the spec.
- Implement strict JSON parsing and validation for LLM output.
- Implement the Phase 3 LLM router with token budgets, usage ledger, and fallback chain before adding any user-facing model selection.
- Include automated backend tests.
- Include clear README setup instructions.
- Do not implement public sharing, novel importing, or China mainland-specific launch features.

Start with Phase 0 and do not skip phases. Complete one phase, run its tests or acceptance checks, summarize files changed, update the memory files, then move to the next phase only after the acceptance gate passes. Start with backend scaffold and tests. After backend fake mode passes, implement iOS screens and integration.

When you make changes, explain:
1. files changed
2. how to run backend
3. how to run tests
4. how to configure the iOS app base URL
5. memory files updated
6. what remains unfinished
```

---

## 28. Definition of Done

The MVP is done when:

- Backend runs locally in fake mode.
- Backend can call Qwen provider when env vars are provided.
- iOS app can create a story.
- iOS app can play turns.
- iOS app can resume saved story.
- App has at least 5 templates.
- App has basic safety redirect.
- App has feedback submission.
- Backend tests pass.
- README has clear setup instructions.
- No LLM key is present in iOS source.
- No third-party novel import feature exists.
- No public sharing feature exists.

---

## 29. Important Product Constraints

Keep the MVP narrow.

The first version should prove one thing:

> Can users enjoy repeatedly playing an AI-generated long-form interactive story with stable memory and satisfying choices?

Everything else can wait.
