# Architecture

## High-level flow

```text
iOS SwiftUI App
  Home
  Template selection
  Protagonist setup
  Play screen
  Story list
  Settings and feedback
        |
        v
FastAPI Backend
  Device session
  Story service
  Turn service
  State manager
  Safety filter
  LLM gateway
  LLM router
  Usage ledger
        |
        v
LLM Provider
  Fake provider for tests
  Qwen or OpenAI-compatible provider later
```

## Core backend modules

- config
- database
- models
- schemas
- services/story_service.py
- services/turn_service.py
- services/state_manager.py
- services/safety_filter.py
- llm/provider.py
- llm/fake_provider.py
- llm/openai_compatible_provider.py
- llm/provider_factory.py
- llm/story_opening.py
- llm/quota.py
- llm/router.py
- tests

## Cloudflare backend deployment adapter

- `worker.py`: Cloudflare Python Worker entrypoint that forwards Workers requests into the existing FastAPI ASGI app.
- `wrangler.jsonc`: safe Cloudflare Worker deployment template for Python Workers compatibility, fake-mode backend vars, observability, and optional KV persistence.
- `python_modules/`: generated Python Worker vendored dependencies; ignored by Git and regenerated with `pywrangler sync`.
- `app/services/cloudflare_story_store.py`: small async KV persistence adapter used only when a Cloudflare KV binding is attached to `app.state.storycat_state`.
- `app/main.py`: registers the same health and API routers both at root and under `/storycat` so deployments can use an optional path-prefix route without changing internal API handlers.
- `app/api/routes/stories.py`: route handlers are async so Python Workers do not need threadpool execution; story create, turn, fetch, and list calls save/load story records through KV when deployed.
- `app/api/routes/feedback.py`: feedback story validation can load the target story from KV before checking ownership.
- `ios/PlayableNovel/AppConfig.swift`: defaults to the local backend base URL and can be changed for your own deployment.

Cloudflare deployment can keep the existing root API route shapes or add the `/storycat` prefix for path-prefix deployments. It is still fake-mode by default and does not ship real LLM provider secrets.

## Phase 0 implemented backend scaffold

- `app/main.py`: FastAPI app factory and ASGI app instance.
- `app/api/routes/health.py`: `GET /health`.
- `app/core/config.py`: Pydantic settings, fake LLM mode defaults, and backend-only API key placeholder.
- `app/db/session.py`: database URL placeholder for later SQLAlchemy or SQLModel integration.
- `tests/`: backend health and config tests.

## Phase 1 implemented backend modules

- `app/api/router.py`: versioned `/v1` API router.
- `app/api/errors.py`: standard validation error response.
- `app/api/routes/device_session.py`: `POST /v1/device-session`.
- `app/api/routes/feedback.py`: `POST /v1/feedback`.
- `app/api/routes/stories.py`: `POST /v1/stories` and story read/turn routes; story creation and turn generation now enter settings-gated service dispatchers, map known provider/router/quota failures to sanitized API errors, and expose optional router and quota dependencies that are disabled by default.
- `app/api/routes/templates.py`: `GET /v1/templates`.
- `app/schemas/device_session.py`: request and response schemas.
- `app/schemas/feedback.py`: feedback request and response schemas.
- `app/schemas/stories.py`: create story request and response schemas.
- `app/schemas/templates.py`: story template response schemas.
- `app/services/device_session_service.py`: in-memory fake-mode device session store.
- `app/services/feedback_service.py`: in-memory fake-mode feedback store.
- `app/services/story_service.py`: in-memory fake-mode story creation, storage, listing, fetching, choice-turn advancement, free-text turn advancement, an internal injected-provider story creation helper for Phase 3 LLM story-opening tests, a settings-gated service dispatcher that keeps fake creation default while selecting provider-factory story creation only when fake mode is disabled, optional in-memory ledger recording for successful and invalid provider-generated story openings, optional router usage accounting for routed story openings, and optional user/story quota usage accounting from story-opening ledger entries.
- `app/services/template_service.py`: in-memory MVP template catalog.

## Phase 2 implemented backend modules

- `app/schemas/state.py`: structured `StoryState` schema for current fake-mode story state, plus `TurnStatePatch` validation models for generated turn result patches.
- `app/services/state_manager.py`: state validation and deterministic fake turn update service; validates fake story state payloads with `StoryState`, validates generated turn state patches with `TurnStatePatch`, applies generated turn patches for progress, summaries, relationships, inventory, stats, and flags, applies choice/free-text state changes for progress, stats, flags, summaries, and relationships, and completes chapter 1 for `xianxia_rise` after the deterministic fake-mode threshold.
- `app/services/safety_filter.py`: small deterministic fake-mode action redirect helper for clearly unsafe, copyrighted-IP, or impossible free-text actions.

## Phase 3 implemented backend modules

- `app/llm/provider.py`: internal LLM provider contract with request/response models, usage metadata, Phase 3 task type constants, and fast/quality model tier mapping.
- `app/llm/fake_provider.py`: deterministic fake LLM provider for tests; returns strict JSON-shaped payloads and estimated token usage without external API calls.
- `app/llm/openai_compatible_provider.py`: disabled-by-default OpenAI-compatible provider skeleton; validates backend-only provider settings, exposes non-secret metadata including transport wiring status, maps task types to fast/quality model names, builds local Chat Completions payloads, adds DeepSeek-only `thinking: disabled` for strict JSON calls, accepts an injected chat transport for local fake response tests, includes an explicitly instantiated stdlib HTTP transport for `{base_url}/chat/completions`, provides a settings-based factory that wires HTTP transport only after fake-mode and missing-config guards pass, parses local/fake response envelopes into `LLMResponse`, and raises typed unavailable or malformed-response errors when transport is missing, fails, returns non-2xx status, or returns a bad envelope.
- `app/llm/provider_factory.py`: app-level provider selection helper that returns `FakeLLMProvider` in fake mode and the settings-wired OpenAI-compatible provider in real-provider mode without calling the provider or opening network access.
- `app/llm/story_opening.py`: internal story-opening LLM helper that builds `story_bible_generation` requests from story creation input and template metadata, optionally selects a quality-tier router model, optionally checks user/story quota preflight before provider generation, applies router-selected provider/model/fallback metadata to the provider response, validates returned title, opening narrative, story bible, plot plan, initial state patch, and choices, raises a typed validation error that preserves invalid provider responses for ledger recording, and assembles validated payloads into the current state-manager-validated `StoryState` shape.
- `app/llm/parser.py`: strict provider raw JSON parser and normal turn generation output validator that reports parse/schema errors as typed results.
- `app/llm/gateway.py`: local normal-turn generation coordinator that can use optional in-memory router selection metadata for the initial normal-turn attempt, returns typed router selection failures before provider calls when no required-tier model is available, can run explicit user/story quota preflight before provider calls, records selected model and user/story quota usage from the initial provider ledger entry, parses provider output from fake or OpenAI-compatible providers, retries once with a `json_repair` task after invalid JSON or schema output, and returns a deterministic local fallback normal-turn payload if repair also fails.
- `app/llm/ledger.py`: in-memory Phase 3 LLM call ledger that records provider attempts, repair attempts, local fallback events, token usage, status, latency, and parse failure metadata.
- `app/llm/quota.py`: in-memory Phase 3 user/story quota policy with monthly token budget preflight, typed quota failure metadata/error wrapper, and local usage accounting from non-fallback ledger entries.
- `app/llm/router.py`: in-memory Phase 3 model router selection layer with fake fast/quality model configs, priority ordering, enabled/health checks, daily/monthly token budget checks, fallback-chain metadata, typed selection failure metadata, and local usage accounting from non-fallback ledger entries.
- `app/services/story_service.py` Phase 3 extensions: internal provider-backed choice-turn and free-text-turn helpers that build `normal_turn_generation` requests from stored story state and player input, call the existing gateway with injected provider/ledger/router/quota dependencies, apply generated `state_patch` through the state manager, store generated turn metadata, reuse free-text safety redirects before provider calls, and expose a service-level settings-gated turn dispatcher for choice/free-text input used by the public turn route.
- `scripts/smoke_real_provider.py`: manual real-provider smoke script gated by `REAL_PROVIDER_SMOKE=1`; calls public story creation and one public choice turn against a separately running backend, checks for provider-opening state, fake-mode/fake-model metadata, and three-choice responses, and prints sanitized metadata only.
- `tests/conftest.py`: pytest LLM settings isolation so local ignored `.env` real-provider credentials do not affect fake-mode automated tests.

## Phase 3 accepted real-provider configuration

- Local ignored `.env` can use `LLM_PROVIDER=deepseek`, `LLM_BASE_URL=https://api.deepseek.com`, `LLM_MODEL_FAST=deepseek-v4-flash`, and `LLM_MODEL_QUALITY=deepseek-v4-pro`.
- Story openings use the quality model and normal turns use the fast model.
- Story-opening and normal-turn prompts include concrete JSON output examples for strict provider schema compliance.
- Real-provider smoke passed on 2026-05-31 without exposing generated text or secrets.

## Core iOS modules

- App entry
- APIClient
- DeviceIDStore
- Local story cache
- HomeView
- TemplateSelectionView
- ProtagonistSetupView
- PlayView
- StoryListView
- SettingsView
- FeedbackView

## Phase 0 implemented iOS scaffold

- `ios/PlayableNovel.xcodeproj`: minimal Xcode project with shared `PlayableNovel` scheme.
- `ios/PlayableNovel/PlayableNovelApp.swift`: SwiftUI app entry.
- `ios/PlayableNovel/ContentView.swift`: placeholder launch view.
- `ios/PlayableNovel/AppConfig.swift`: backend base URL and default locale; no LLM API key is stored in iOS.
- `ios/PlayableNovel/Assets.xcassets`: minimal asset catalog and accent color.

## Phase 4 implemented iOS API boundary

- `ios/PlayableNovel/APIModels.swift`: Swift Codable models for the existing backend public routes, including device session, templates, protagonist profile, story creation, story fetch/list, turns, feedback, and standard error envelopes.
- `ios/PlayableNovel/APIModels.swift`: `JSONValue` typed dynamic JSON wrapper for story state payloads and backend error details.
- `ios/PlayableNovel/APIClient.swift`: small `URLSession` client using `AppConfig.backendBaseURL`, JSON request bodies, response decoding, and sanitized API error-envelope handling.
- The iOS client boundary calls only existing backend routes and stores no LLM provider API keys.

## Phase 4 implemented iOS identity/session boundary

- `ios/PlayableNovel/DeviceIDStore.swift`: Keychain-backed anonymous device UUID persistence.
- `ios/PlayableNovel/DeviceSessionBootstrapper.swift`: loads or creates the local device ID, calls the backend device-session route through `APIClient`, and returns `DeviceSessionState`.
- `ios/PlayableNovel/AppConfig.swift`: centralizes the backend base URL, default locale, and app version used by session bootstrap.
- Session bootstrap has protocol-based test seams for the device ID store and session API; the app still has no user-facing model selection or LLM API key storage.

## Phase 4 implemented iOS launch/home state boundary

- `ios/PlayableNovel/LaunchHomeViewModel.swift`: `ObservableObject` state boundary for launch/home loading.
- The view model calls `DeviceSessionBootstrapper.bootstrap()` and then `APIClient.fetchTemplates`.
- Launch/home state is represented as idle, loading, loaded with session plus templates, or failed with a safe message.
- The view model has injected protocol dependencies for local checks without Keychain mutation or network access.

## Phase 4 implemented iOS launch/home UI surface

- `ios/PlayableNovel/ContentView.swift`: minimal SwiftUI surface connected to `LaunchHomeViewModel`.
- The view starts launch loading from idle state, shows loading progress, backend error/retry, daily turn usage, and a read-only template list.
- Story creation navigation and protagonist setup are intentionally left for later Phase 4 tasks.

## Phase 4 implemented iOS template/protagonist setup state

- `ios/PlayableNovel/ContentView.swift`: template rows can be selected from the loaded launch/home template list.
- `ios/PlayableNovel/ContentView.swift`: `ProtagonistSetupDraft` stores the local protagonist setup form fields and validates required inputs before story creation exists.
- Valid draft state maps into the existing `ProtagonistProfile` request model, but no story creation API call is made in this task.

## Phase 4 implemented iOS story creation action

- `ios/PlayableNovel/ContentView.swift`: `StoryCreating` is the small story-creation client boundary, with `APIClient` as the default implementation.
- `ios/PlayableNovel/ContentView.swift`: `ProtagonistSetupDraft` can build a `CreateStoryRequest` from the selected template and device session.
- `ios/PlayableNovel/ContentView.swift`: story creation state tracks idle, creating, failed, and created results, then displays the returned title, opening narrative, and choices as read-only content.
- Play-turn submission, free-text input, story resume, feedback, and local cache remain separate later Phase 4 tasks.

## Phase 4 implemented iOS suggested-choice turn action

- `ios/PlayableNovel/ContentView.swift`: `TurnPlaying` is the small turn client boundary, with `APIClient` as the default implementation.
- `ios/PlayableNovel/ContentView.swift`: created-story choices can call `APIClient.playTurn` with `PlayTurnRequest.choice`.
- `ios/PlayableNovel/ContentView.swift`: turn state tracks idle, playing, failed, and played results, then displays the latest narrative, chapter progress, and returned choices as read-only content.
- Repeated choice flow from latest-turn choices, story resume, feedback, and local cache remain separate later Phase 4 tasks.

## Phase 4 implemented iOS free-text turn action

- `ios/PlayableNovel/ContentView.swift`: created stories now expose a minimal free-text action field and submit button.
- `ios/PlayableNovel/ContentView.swift`: free-text actions call `APIClient.playTurn` through the existing `TurnPlaying` boundary with `PlayTurnRequest.freeText`.
- `ios/PlayableNovel/ContentView.swift`: free-text turns reuse the same idle, playing, failed, and played `StoryTurnState` used by suggested-choice turns.
- Story resume, feedback, local cache, repeated choice flow from latest-turn choices, and UI polish remain separate later Phase 4 tasks.

## Phase 4 implemented iOS local story cache boundary

- `ios/PlayableNovel/LocalStoryCache.swift`: SwiftData `LocalStory` and `LocalTurn` models store the minimum fields needed for Phase 4 resume.
- `ios/PlayableNovel/LocalStoryCache.swift`: `StoryCaching` is the local cache boundary, with `SwiftDataStoryCache` as the default implementation over `ModelContext`.
- `ios/PlayableNovel/PlayableNovelApp.swift`: registers the SwiftData model container for `LocalStory` and `LocalTurn`.
- `ios/PlayableNovel/ContentView.swift`: successful story creation and successful choice/free-text turns write to the cache through the boundary without blocking the play flow.
- Story list UI, backend resume fetch, feedback, and UI polish remain separate later Phase 4 tasks.

## Phase 4 implemented iOS cached story list surface

- `ios/PlayableNovel/ContentView.swift`: reads locally cached `LocalStory` rows through a SwiftData `@Query` sorted by updated time.
- `ios/PlayableNovel/ContentView.swift`: shows read-only cached story summaries with title, template ID, chapter, turn count, and updated time in the loaded home list.
- Backend resume fetch/open-story behavior, feedback, repeated latest-turn choices, and UI polish remain separate later Phase 4 tasks.

## Phase 4 implemented iOS cached story open action

- `ios/PlayableNovel/ContentView.swift`: defines a small `StoryFetching` boundary, with `APIClient` as the default implementation for `GET /v1/stories/{story_id}`.
- `ios/PlayableNovel/ContentView.swift`: cached story rows can open the backend canonical story and show loading, error, or opened state.
- `ios/PlayableNovel/ContentView.swift`: opened cached stories display title, state summary fields, and latest turns as read-only content.
- Resumed choice continuation, resumed free-text input, feedback, and UI polish remain separate later Phase 4 tasks.

## Phase 4 implemented iOS resumed suggested-choice action

- `ios/PlayableNovel/ContentView.swift`: parses suggested choices from the last fetched `GetStoryResponse.latestTurns` entry when the entry includes a `choices` array.
- `ios/PlayableNovel/ContentView.swift`: opened cached stories can submit one resumed suggested-choice turn through the existing `TurnPlaying` boundary and `APIClient.playTurn`.
- `ios/PlayableNovel/ContentView.swift`: resumed choice turns reuse `StoryTurnState`, the existing latest-turn display, and the `StoryCaching` write path.
- Resumed free-text input, feedback, new backend routes, and iOS LLM API keys remain separate later Phase 4 tasks.

## Phase 4 implemented iOS resumed free-text action

- `ios/PlayableNovel/ContentView.swift`: opened cached stories now expose a minimal free-text continuation field.
- `ios/PlayableNovel/ContentView.swift`: resumed free-text actions call `APIClient.playTurn` through `TurnPlaying` with `PlayTurnRequest.freeText`.
- `ios/PlayableNovel/ContentView.swift`: resumed free-text turns reuse `StoryTurnState`, the existing latest-turn display, and the `StoryCaching` write path.
- Feedback, settings, UI polish, new backend routes, and iOS LLM API keys remain separate later Phase 4 tasks.

## Phase 4 implemented iOS feedback submit action

- `ios/PlayableNovel/ContentView.swift`: defines a small `FeedbackSubmitting` boundary, with `APIClient` as the default implementation for `POST /v1/feedback`.
- `ios/PlayableNovel/ContentView.swift`: latest played turns expose a minimal feedback reason field and submit action.
- `ios/PlayableNovel/ContentView.swift`: feedback submission sends `device_id`, `story_id`, `turn_id`, a fixed neutral rating, and the user-entered reason.
- Settings, analytics, UI polish, new backend routes, and iOS LLM API keys remain separate later tasks.

## Phase 4 accepted iOS MVP flow

- The accepted Phase 4 app flow uses the existing backend routes for device session, templates, story creation, story fetch, turn play, and feedback.
- `ContentView` is still a minimal technical surface, but it now covers the required create, play, resume, and feedback paths.
- SwiftData local cache stores local story and turn summaries for resume, while the backend remains the canonical story-state source.
- The iOS app contains no LLM provider API key, no raw provider response surface, and no user-facing model selector.
- Phase 5 should improve playability and state visibility without changing the backend route shape unless a narrow polish task proves a route change is necessary.

## Phase 5 implemented backend polish

- `app/services/story_service.py` keeps fake-mode turn generation deterministic while replacing the repeated static next-choice set with turn-aware variants.
- `app/services/story_service.py` now uses template-aware deterministic scene beats for fake-mode choice/free-text turns and keeps user-facing narrative free of developer labels such as `Fake mode` and repeated chapter/scene boilerplate such as `第 X 章的第 Y 幕`.
- `app/services/story_service.py` now formats fake-mode opening, choice turns, and free-text turns as multi-paragraph story pages so choices come after a fuller scene beat and key decision setup.
- `app/services/story_service.py` now assigns fake-mode turns to chapter pacing stages (`setup`, `pressure`, `reveal`, `turning_point`) and uses those stages to vary narrative intent and next-choice labels.
- Provider-backed normal-turn requests now include `chapter_pacing` in the prompt payload and `chapter_pacing_stage` / `chapter_pacing_directive` in request metadata so real providers can follow the same chapter rhythm without changing the public API.
- `app/llm/fake_provider.py` and `app/llm/gateway.py` mirror the same stage-aware three-choice shape for provider-path tests and deterministic fallback behavior.
- Fake-mode turn responses still return exactly three choices with stable `choice_1`, `choice_2`, and `choice_3` IDs and low/medium/high risk coverage.
- `app/services/state_manager.py` rolls later fake-mode chapters into the next chapter at the scene boundary so `chapter_progress` does not stay pinned at 100% while scene count keeps increasing.
- The public story and turn route shapes, provider configuration, real-provider path, and iOS LLM-key boundary are unchanged.

## Phase 5 implemented iOS playability polish

- `ios/PlayableNovel/ContentView.swift` now makes direct latest-turn choices actionable after a created-story choice or free-text turn.
- Opening choices, direct latest-turn choices, and resumed-story choices reuse the same internal choice-turn helper over `TurnPlaying` and `PlayTurnRequest.choice`.
- Repeated direct-play turns continue to write through the existing `StoryCaching` path and keep provider keys out of iOS.
- `ios/PlayableNovel/ContentView.swift` now parses latest-turn `state.relationships` and `state.inventory` through a small visible-state snapshot helper and shows compact relationship and item summary lines in the direct latest-turn surface.
- `ios/PlayableNovel/ContentView.swift` localizes relationship display labels so known backend character IDs and statuses do not appear as raw technical codes.
- `ios/PlayableNovel/ContentView.swift` now includes a compact `AIContentNoticeView` in the loaded play flow, backed by local copy constants and no backend API dependency.
- `ios/PlayableNovel/ContentView.swift` now keeps protagonist setup friction low by generating template-aware personality, starting role, main goal, special ability, and tone locally before sending the existing story-creation request.
- `ios/PlayableNovel/ContentView.swift` now owns a first visual-component layer for loading, error, session summary, template rows, generated setup, narrative blocks, and choice rows while staying inside the existing single-screen MVP flow.
- `ios/PlayableNovel/ContentView.swift` now presents a branded loading surface with root background coverage during launch/backend loading states.
- `ios/PlayableNovel/AppConfig.swift` now includes `AppBrand` constants for StoryCat / 故事猫, by Station Cat, App Store titles, and one-line introductions.
- `ios/PlayableNovel.xcodeproj` sets the generated iOS display name to `StoryCat`.
- `ios/PlayableNovel/ContentView.swift` now keeps `latestPlayedTurn` as the stable current play surface while `StoryTurnState` tracks transient loading, failure, and played status, preventing the latest-turn choices from disappearing during continuation.
- `ios/PlayableNovel/ContentView.swift` now includes a reusable `StoryBookPageView`, page-corner/edge visuals, and a custom `bookPageTurn` transition so opening pages, latest turns, and reopened recent turns can render as book-like pages without changing backend data shapes.
- `ios/PlayableNovel/ContentView.swift` uses `StoryTurnState.playing` to show a page-turn overlay on the current story page while a choice or free-text turn request is in flight.
- `ios/PlayableNovel/ContentView.swift` now uses a custom ScrollView bookshelf flow for the loaded state instead of system List sections, with `StoryTemplateBookshelfView`, `CachedStoryBookshelfView`, and `SelectedStoryBookSetupView` composing shelf, book-cover, and role-setup surfaces.
- StoryCat book pages and role setup surfaces use fixed paper/ink colors and a light color scheme to avoid unreadable white-on-paper text in iOS dark mode.
- `ios/PlayableNovel/Assets.xcassets/AppIcon.appiconset` now contains the first Station Cat-style iOS app icon, connected through the target asset catalog setting.
- `ios/PlayableNovel/LaunchScreen.storyboard` provides the static warm StoryCat launch screen used before SwiftUI renders.

## LLM router requirements

- Supports model-level token budgets.
- Supports daily and monthly budgets.
- Supports fallback model chain.
- Records input tokens, output tokens, latency, provider, model, and error.
- Never exposes API keys to the client.
