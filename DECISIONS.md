# Decisions

## D001: Start with overseas Chinese users

Reason:
- Reduces China mainland regulatory complexity in the MVP stage.
- Keeps the first market aligned with Chinese web-novel taste while avoiding early compliance overload.

## D002: Do not import existing novels in MVP

Reason:
- Avoids copyright and derivative work risk.
- Keeps the product focused on original AI-generated stories.

## D003: No public UGC sharing in MVP

Reason:
- Reduces content moderation, copyright, and App Store review risk.
- Private play is enough to validate the core loop.

## D004: Fake mode before real LLM integration

Reason:
- Allows backend, iOS, and state logic to be tested without API cost or model instability.

## D005: LLM keys stay only on the backend

Reason:
- Protects secrets.
- Allows quota control, routing, logging, safety checks, and provider replacement.

## D006: Real LLM integration requires quota routing

Reason:
- Prevents uncontrolled token spending.
- Enables model fallback when a provider or budget is unavailable.

## D007: Redirect invalid free-text actions in the story response envelope

Reason:
- A story-friendly redirect keeps the play screen in the narrative loop instead of turning every invalid action into a hard API error.
- Redirected actions should not advance chapter progress or mutate game state.

## D008: Use a deterministic fake threshold for first chapter completion

Reason:
- Completing `xianxia_rise` chapter 1 on the sixth valid normal turn gives Phase 2 a testable chapter-complete gate without adding complex branching.
- Redirected actions do not count toward the threshold because they do not mutate story state.

## D009: Start Phase 3 with an internal provider contract

Reason:
- A stable request/response contract lets fake mode, parser validation, routing, and real provider adapters be tested independently.
- The fake provider must not require API keys or network access, so backend tests remain deterministic.

## D010: Parse provider output into typed results instead of raising

Reason:
- JSON parser failures and schema failures need to feed repair retry, fallback, and logging paths.
- Returning `invalid_json` or `invalid_schema` keeps malformed model output from crashing the app layer.

## D011: Retry malformed normal-turn JSON once before fallback

Reason:
- A single deterministic repair attempt matches the MVP spec while keeping model calls bounded.
- Recording both the initial parse failure and final repair result prepares the path for provider logging and fallback decisions.

## D012: Use deterministic local normal-turn fallback after repair failure

Reason:
- If both initial parsing and the bounded repair attempt fail, the play loop still needs a valid normal-turn result instead of exposing provider failure to the app.
- The fallback stays local, deterministic, and schema-validated, while preserving initial and repair parse failure metadata for later logging.

## D013: Start LLM usage tracking with an in-memory ledger

Reason:
- Phase 3 needs token, latency, status, and fallback tracking before quota routing and real provider calls are wired in.
- Keeping the first ledger in-memory preserves deterministic fake-mode tests and avoids adding persistence before the router contract is stable.

## D014: Start model routing with deterministic in-memory selection

Reason:
- The router needs testable budget and fallback behavior before it is allowed to call real providers.
- A local model config list keeps fake-mode routing deterministic while preserving the same tier, priority, health, and budget concepts required for the later persistent router.

## D015: Count provider ledger usage before real calls are wired

Reason:
- Provider attempts consume model budget even when the returned JSON later fails parsing, so non-fallback ledger entries should increment model usage.
- Local deterministic fallback does not represent an external provider model call and should not spend provider model budget.

## D016: Wire router selection as metadata before real provider dispatch

Reason:
- Fake-mode tests need to prove router fallback metadata before real model clients exist.
- Keeping no-router behavior unchanged lets existing deterministic fake provider tests remain stable while router-aware paths opt in explicitly.

## D017: Record gateway router usage from the initial provider ledger entry

Reason:
- The ledger entry is the source of truth for provider, model, token usage, latency, fallback flag, and parse status.
- Counting the initial provider attempt immediately lets the next router selection see exhausted budgets without adding real provider calls.
- Deterministic local fallback output is not a provider model call, so it must not spend provider model budget.

## D018: Return typed router selection failures before provider calls

Reason:
- When every model in a required tier is unavailable, the failure is a quota/routing decision rather than malformed model output.
- Returning a typed internal result preserves skipped model metadata for logging and future API error mapping.
- The provider and usage ledger should not be touched when no model was selected.

## D019: Keep user/story quota preflight explicit in fake mode

Reason:
- Existing fake-mode provider tests should remain deterministic unless a quota policy is passed intentionally.
- A pre-provider quota failure is a budget control result, so it should return a typed internal failure rather than invoking repair or local fallback.
- User and story quota checks need their own metadata because they are separate from model-level router budget failures.

## D020: Record user/story quota usage from provider ledger entries

Reason:
- The same ledger entry used for model accounting is the stable source for actual or estimated token usage.
- User and story quota usage should advance only for provider attempts, not deterministic local fallback output.
- Returning typed quota usage updates keeps the later persistent quota service and API error mapping observable without adding persistence yet.

## D021: Add real-provider config skeleton before network calls

Reason:
- Phase 3 needs provider settings, metadata, and typed failure behavior before any external request is allowed.
- Fake mode must remain the default so local tests do not require API keys or network access.
- Exposing non-secret metadata first lets router/provider wiring be tested without leaking the API key.

## D022: Parse OpenAI-compatible envelopes locally before transport wiring

Reason:
- Chat Completions payload shape and response envelope parsing can be tested with local fixtures before any real provider call is allowed.
- Keeping payload construction separate from transport reduces API-key leakage risk and makes router-selected model names observable.
- Typed malformed-envelope failures keep provider adapter errors consistent with the existing parser, repair, fallback, and ledger paths.

## D023: Wire provider generate through injected transport first

Reason:
- An injected transport lets `generate` exercise payload construction and response parsing without opening real network access.
- Keeping no-transport behavior as `provider_unavailable` preserves the disabled-by-default safety guard.
- The same transport boundary can later host the real HTTP implementation while local fake tests continue to prove model selection and error mapping.

## D024: Use stdlib HTTP transport with explicit instantiation

Reason:
- The real-provider transport should not add a new runtime dependency while the app is still in Phase 3 adapter hardening.
- Explicit transport instantiation keeps default tests and fake mode from accidentally opening network access.
- Mapping HTTP status and JSON decode failures to typed provider errors keeps the HTTP layer compatible with the existing repair, fallback, and logging paths.

## D025: Prove real-provider gateway behavior with mocked HTTP first

Reason:
- The normal-turn gateway must see OpenAI-compatible provider responses exactly like any other provider before real endpoint calls are allowed.
- Mocked HTTP envelopes let ledger metadata, repair retry, and deterministic fallback behavior be tested without cost or network instability.
- Keeping this as a local-only test step preserves the real-provider boundary until settings-based wiring and manual smoke checks are explicit.

## D026: Wire OpenAI provider construction from settings without calls

Reason:
- Provider construction needs to be settings-driven before app-level selection can choose fake mode or real-provider mode.
- Transport wiring should happen only after fake-mode and missing-config guards pass.
- Exposing only a boolean transport status in metadata makes wiring testable without revealing secrets or opening network access.

## D027: Keep app-level provider selection thin and side-effect free

Reason:
- Fake mode should choose `FakeLLMProvider` before any real-provider configuration checks so local development remains API-key free.
- Real-provider mode should delegate to the OpenAI-compatible settings factory so missing config remains a typed provider error.
- Selection should only construct the provider, not call it, so app startup and dependency wiring cannot accidentally spend tokens or open network access.

## D028: Validate story-opening provider output before route wiring

Reason:
- Story creation needs a quality-model opening path, but the public fake-mode route should stay stable while the internal LLM contract is hardened.
- A dedicated story-opening payload schema catches malformed story bible, plot plan, and choice output before state assembly or persistence is introduced.
- Testing with `FakeLLMProvider` first keeps story-opening integration deterministic and API-key free.

## D029: Assemble story-opening state before service route wiring

Reason:
- The real-provider story creation path needs to prove it can produce the same `StoryState` shape that the Phase 2 state manager already validates.
- Keeping assembly internal avoids changing public fake-mode route behavior before the service-level LLM path is testable.
- Initial state assembly should validate through the existing state manager so later route wiring cannot introduce malformed story state.

## D030: Add the LLM story creation path as an injected service helper first

Reason:
- Story creation needs to prove the provider-generated opening can become a stored `StoryRecord` before route-level settings dispatch is introduced.
- Direct provider injection keeps local tests deterministic and avoids accidental external model calls.
- Leaving the public route on deterministic fake creation preserves Phase 1 and Phase 2 acceptance behavior while Phase 3 integration hardens.

## D031: Gate service-level story creation by backend settings before route wiring

Reason:
- Fake mode must remain the default path for deterministic local development and tests.
- Real-provider story creation should only be selected when backend settings explicitly disable fake mode.
- Unknown templates should be rejected before provider construction so not-found behavior cannot accidentally trigger provider setup or external calls.
- Keeping the dispatcher at service level first makes the later public route wiring small and reviewable.

## D032: Route story creation through the settings-gated dispatcher

Reason:
- Public story creation needs the same fake-mode and real-provider-mode selection boundary as the service layer.
- Keeping provider-factory selection as a FastAPI dependency makes fake-disabled route tests local and API-key free.
- The route should continue returning the existing deterministic fake response by default until real-provider smoke checks are explicitly run.

## D033: Sanitize public story creation provider failures

Reason:
- Provider configuration and generation failures should not leak backend settings, raw provider messages, provider names, response text, or API keys to iOS.
- A stable `story_generation_unavailable` API error lets the client show a safe retry message while backend logs and ledger work evolve separately.
- Unknown templates should keep their existing `template_not_found` response and should still be resolved before provider construction.

## D034: Record successful story-opening provider calls in the in-memory ledger

Reason:
- Story creation uses the quality-model `story_bible_generation` task and should be visible in the same Phase 3 ledger concept as normal turns.
- Keeping the first story-opening ledger path in-memory avoids adding persistence before the contract is stable.
- Fake-mode deterministic story creation is not a provider call and should not spend or record provider model usage.

## D035: Record invalid story-opening provider responses before sanitizing API errors

Reason:
- Provider responses that fail story-opening schema validation still consumed a model call and need token, latency, provider, model, and failure metadata in the Phase 3 ledger.
- The public API should continue returning only the stable `story_generation_unavailable` error so raw provider output and schema details do not leak to iOS.
- Keeping the invalid-output path in-memory and test-injected avoids adding persistence or external provider calls before router usage is wired into story creation.

## D036: Keep story-opening router injection explicit

Reason:
- Story creation uses the quality-tier `story_bible_generation` task, so it should be able to use the same in-memory router fallback metadata as normal turns.
- The public route should not default to the fake router in real-provider mode because that could overwrite real provider/model metadata with fake model names.
- An explicit optional router dependency keeps tests local and deterministic while preserving the current fake-mode and un-routed provider defaults.
- Router selection failures should be sanitized at the API boundary and should not create provider ledger entries because no provider call was made.

## D037: Count story-opening quota usage only after provider attempts

Reason:
- Story-opening quota preflight should happen before provider generation so exhausted user or story budgets cannot spend tokens.
- User and story quota usage should advance from the same initial ledger entry used for provider/model accounting, including schema-invalid provider output because it still consumed a provider call.
- The public route should not default to an in-memory quota policy yet because persistence and user identity binding are not stable in this phase.
- Quota failure API responses should expose stable reason codes only, not budget amounts, usage totals, or internal subject IDs.

## D038: Add provider-backed choice turns as an internal helper before route wiring

Reason:
- Turn generation needs to prove that a normal-turn provider result can mutate stored story state before public route dispatch changes.
- Keeping the helper internal preserves deterministic fake-mode `POST /v1/stories/{story_id}/turns` behavior while Phase 3 integration hardens.
- Reusing the existing normal-turn gateway keeps router, quota, repair, fallback, ledger, and provider metadata behavior in one tested path.

## D039: Reuse safety redirects before provider-backed free-text turns

Reason:
- Free-text input can contain unsafe, copyrighted-IP, or impossible actions, so provider-backed turns should preserve the existing story-friendly redirect boundary before any provider call.
- Redirected actions should still avoid provider generation, ledger writes, token spend, and state mutation.
- Keeping the free-text helper internal preserves public fake-mode route behavior while proving the normal-turn gateway path for valid free-text actions.

## D040: Gate provider-backed turns at the service layer before public route wiring

Reason:
- Public turn routing should be a small follow-up once fake-mode and provider-backed turn paths share one service dispatcher.
- The dispatcher keeps fake mode deterministic by default and constructs providers only for valid turn input when fake mode is disabled.
- Injecting provider factory, ledger, router, and quota at the service layer keeps route tests local and avoids external provider calls.

## D041: Sanitize public provider-backed turn failures

Reason:
- Turn generation failures can include provider configuration, transport, router, quota, or generated-state validation details that must not leak to iOS.
- A stable `turn_generation_unavailable` API error lets clients show a retry state while preserving internal reason codes for local tests and later logging.
- Existing fake-mode `invalid_choice`, `missing_user_text`, and `story_not_found` behavior should remain unchanged when the public route starts using the dispatcher.

## D042: Keep real-provider smoke testing manual and explicitly opt-in

Reason:
- A real-provider smoke check is needed to prove public story creation and turn generation after the settings-gated routes are wired.
- The check must stay outside automated tests so local fake-mode test runs never spend tokens, require API keys, or depend on external provider uptime.
- The smoke script should call only backend public endpoints, rely on backend environment variables for provider credentials, and avoid printing generated story text or raw provider responses.

## D043: Disable DeepSeek thinking mode for strict JSON provider calls

Reason:
- Phase 3 real-provider smoke requires schema-valid JSON for story openings and normal turns.
- DeepSeek V4 defaults can return thinking-mode content that does not satisfy the app's strict JSON schema.
- Adding `thinking: {"type": "disabled"}` only for `LLM_PROVIDER=deepseek` keeps other OpenAI-compatible providers unchanged while improving DeepSeek JSON-mode reliability.

## D044: Keep pytest isolated from local real-provider `.env`

Reason:
- Developers need a local ignored `.env` for real-provider smoke checks.
- Automated tests must remain fake-mode, deterministic, and external-call free even when `.env` points at DeepSeek.
- A pytest fixture forces fake-mode LLM settings for test runs, while specific tests can still override settings explicitly.

## D045: Keep iOS API decoding explicit and backend-keyed

Reason:
- Phase 4 iOS integration should mirror the current public backend contract before UI flow work begins.
- Explicit Swift `CodingKeys` keep snake_case API fields stable without applying global decoder key conversion to dynamic story-state dictionaries.
- Dynamic backend payloads such as `current_state`, turn `state`, `latest_turns`, and error `details` use a typed `JSONValue` wrapper instead of `[String: Any]` or raw strings so later UI/cache code can inspect nested state safely.
- The iOS `APIClient` uses `AppConfig.backendBaseURL` only and does not contain provider names, model selection, or LLM API keys.

## D046: Store the anonymous iOS device ID in Keychain

Reason:
- The Phase 4 launch flow requires a stable anonymous device ID before the app can call `POST /v1/device-session`.
- Keychain persistence better matches the project stack and survives normal app relaunches more reliably than view state or temporary storage.
- The bootstrapper uses injected protocols for the device ID store and session API so launch behavior can be tested without mutating Keychain or calling the backend.
- The device ID is not an LLM credential and no provider API key is stored in iOS.

## D047: Keep launch/home API orchestration in a small view model

Reason:
- Phase 4 needs the iOS app to load a session and templates before building story creation screens.
- A dedicated launch/home view model keeps loading, loaded, and error states testable without network calls or SwiftUI UI assertions.
- Injecting session bootstrap and template-fetching protocols keeps the default app path simple while preserving local deterministic checks.
- Story creation UI should remain a separate next task so the launch/home API boundary can be verified first.

## D048: Make the first home UI read-only

Reason:
- The current Phase 4 task is only to surface launch loading, backend errors, and loaded templates in `ContentView`.
- Keeping template rows read-only avoids starting protagonist setup or story creation before the template list surface is compiled and checked.
- The next task can add template selection and protagonist setup state without changing the already-tested launch/session/template loading boundary.

## D049: Validate protagonist setup locally before story creation

Reason:
- Phase 4 should let the user select a template and fill the required protagonist fields before the app starts calling story creation.
- Local validation keeps missing required fields out of `POST /v1/stories` and makes the next API-wiring task smaller.
- The setup draft maps to the existing `ProtagonistProfile` model, but this task deliberately does not call the backend yet.

## D050: Show created stories before enabling play turns

Reason:
- Phase 4 should prove the iOS app can call `POST /v1/stories` and safely display the returned opening before adding turn submission.
- Keeping returned choices read-only in this task avoids mixing story creation, play-turn state, resume, feedback, and local cache in one change.
- The iOS story creation client boundary is injectable so request construction and response handling can be checked without a live backend.

## D051: Add suggested-choice turns before free-text turns

Reason:
- Suggested choices are the safest first iOS play action because the backend already supplies valid `choice_id` values.
- A choice-only turn step proves `POST /v1/stories/{story_id}/turns` wiring, loading state, error state, and latest-turn display before adding free-text validation and safety redirects.
- Returned turn choices stay read-only in this task so repeated-turn, free-text, resume, and cache state can remain separate later steps.

## D052: Reuse the same iOS turn state for free-text input

Reason:
- Free-text turns should prove the existing backend `input_type=free_text` path from iOS without adding a second play state machine.
- Reusing the current turn loading, error, and latest-turn display keeps the Phase 4 app flow narrow and makes choice/free-text behavior easier to compare.
- The iOS app sends only the player action text and device/story IDs to the backend; safety redirects, quota, model routing, and provider keys remain backend responsibilities.

## D053: Add the iOS local cache boundary before resume UI

Reason:
- Phase 4 resume needs local persistence, but showing and opening previous stories should stay separate from defining the persisted shape.
- A small `StoryCaching` boundary lets story creation and turn submission write cache data now while keeping future resume UI testable.
- The cache stores story and turn payload summaries only; provider secrets, model selection controls, raw provider responses, and backend-only configuration stay out of iOS persistence.

## D054: Show cached story summaries before opening them

Reason:
- Phase 4 resume should first prove that locally cached stories can be surfaced after launch from SwiftData.
- Keeping cached rows read-only avoids mixing local persistence, backend resume fetch, play-state restoration, and feedback in one change.
- The cached list shows only title, template ID, chapter, turn count, and updated time; LLM provider keys, model selection, and raw provider responses remain out of iOS.

## D055: Open cached stories through the backend before continuing play

Reason:
- Phase 4 resume needs to verify the backend's canonical story state before enabling resumed play actions.
- Calling the existing `GET /v1/stories/{story_id}` route keeps the resume path inside the current API contract and avoids adding a new route.
- The first open action stays read-only so choice continuation, resumed free-text input, and feedback can be implemented as separate small tasks.

## D056: Continue resumed stories from latest-turn choices before resumed free-text

Reason:
- Suggested choices from `latest_turns` are the narrowest continuation path after a cached story is reopened.
- Reusing `POST /v1/stories/{story_id}/turns` with `PlayTurnRequest.choice` keeps resume continuation inside the existing API contract.
- The app parses only typed choice data from the fetched story payload and keeps resumed free-text, feedback, new routes, and iOS LLM keys deferred.

## D057: Reuse the free-text turn path for reopened stories

Reason:
- Reopened cached stories should support player-authored continuation even when fetched `latest_turns` does not contain choices.
- Reusing the existing `PlayTurnRequest.freeText`, `TurnPlaying`, `StoryTurnState`, and cache write path keeps resumed play behavior aligned with newly created stories.
- The implementation stays inside the existing turn route and keeps feedback, settings, UI polish, new routes, and iOS LLM keys deferred.

## D058: Tie first iOS feedback submission to the latest played turn

Reason:
- Phase 4 only needs to prove that iOS can submit feedback through the existing backend route before adding a full feedback screen.
- Attaching feedback to `StoryTurnState.played` gives the backend `story_id` and `turn_id` without introducing extra navigation or analytics.
- A fixed neutral rating plus a user-entered reason keeps the first feedback path small while preserving backend ownership checks and avoiding new API shapes.

## D059: Start Phase 5 with a manual 20-turn QA script

Reason:
- Phase 4 acceptance proves the technical iOS flow, but Phase 5 needs a baseline tester path before changing prompts, templates, or visual hierarchy.
- A 20-turn script turns subjective polish into observable checks: coherence, choice differentiation, visible state, resume behavior, and feedback submission.
- Starting with QA keeps Phase 5 scoped and avoids polishing blindly before the product has a repeatable playability yardstick.

## D060: Keep fake-mode suggested choices deterministic but turn-aware

Reason:
- Phase 5 needs fake-mode choices to feel meaningfully different across a 20-turn baseline without depending on real-provider cost or network access.
- Stable `choice_1`, `choice_2`, and `choice_3` IDs keep the iOS and backend contract unchanged while allowing labels to vary by turn.
- Preserving low/medium/high risk coverage keeps automated and manual QA able to exercise cautious, committed, and risky paths.

## D061: Reuse the same iOS choice-turn path for direct latest-turn choices

Reason:
- Phase 5 needs the direct play surface to support continuous suggested-choice play after each returned turn.
- Reusing `TurnPlaying`, `PlayTurnRequest.choice`, and the existing cache write path keeps behavior aligned with opening choices and resumed-story choices.
- Keeping the implementation inside `ContentView` avoids new routes, new persistence shapes, model-provider changes, or iOS LLM keys.

## D062: Roll fake-mode chapters forward at scene boundaries

Reason:
- Phase 5 20-turn QA found that chapter progress became misleading when `progress_percent` stayed at 100% while scene count kept increasing.
- Rolling later fake-mode chapters into the next chapter at a fixed scene boundary keeps progress understandable without adding a new API field.
- Keeping the same `chapter_progress` object preserves the iOS and backend contract while making the existing indicator useful across longer fake-mode baselines.

## D063: Read visible iOS state from the existing turn payload

Reason:
- Phase 5 needs state changes to be visible without widening the backend API or adding new iOS persistence.
- Parsing `state.relationships` and `state.inventory` from the existing `PlayTurnResponse.state` keeps the public contract stable and uses the current `JSONValue` boundary.
- Keeping the display compact inside the latest-turn surface improves tester visibility while preserving the technical MVP UI style.

## D064: Keep the first AI content notice compact in Phase 5

Reason:
- Phase 5 needs a visible AI-generated content notice for playability testing, but full legal, safety, privacy, and TestFlight readiness belong to Phase 6.
- Placing a concise notice in the loaded iOS play flow makes it visible before story creation and play without changing backend routes or provider behavior.
- The notice reminds users not to enter copyrighted works, private personal information, or illegal content while keeping the MVP technical flow lightweight.

## D065: Auto-generate nonessential protagonist setup on iOS

Reason:
- Real-device feedback showed the MVP setup felt rough, and asking players to fill personality, starting role, main goal, and special ability creates too much friction before play.
- Generating those fields from the selected template keeps the existing `CreateStoryRequest` and backend validation intact while reducing player input to name and pronouns.
- A local `换一组` action gives players control without adding backend routes, model calls, account state, or user-facing provider settings.

## D066: Match the first app icon to the Station Cat brand tone

Reason:
- The app should feel like part of the Station Cat product family rather than a generic fantasy-novel tool.
- The icon uses the existing website-inspired palette and a small creative notebook/story-branch motif, then connects through the standard iOS asset catalog.
- Icon generation and asset wiring stay inside Phase 5 visual polish and do not affect backend routes, API contracts, model providers, or iOS secrets.

## D067: Preserve the latest played turn during continuation

Reason:
- Real-device validation showed the story could appear to stop around the second round even though the backend fake-mode turn route could keep generating choices.
- Keeping the latest successful turn separately from the loading/failure state prevents the current play surface from disappearing while the next request is in flight or after a transient failure.
- The fix stays inside iOS UI state and does not change backend routes, API response shapes, provider configuration, or iOS secret boundaries.

## D068: Defer book-style page-turn UI until continuation is validated

Reason:
- A page-turn transition can make the next-round interaction feel like flipping to a new page, matching the product direction better than plain list updates.
- The current task is a blocker fix, so presentation animation should wait until the user confirms basic multi-turn continuation works on a real device.
- Keeping the page-turn work as a later Phase 5 task avoids mixing UX motion design with the state bug fix.

## D069: Keep fake-mode deterministic but remove developer-facing copy

Reason:
- Fake mode is still useful for local testing and quota-free validation, but players should not see implementation labels such as `Fake mode`, `npc_001`, or `unknown`.
- Deterministic template-aware scene beats make repeated fake-mode turns feel more like a story while preserving stable test behavior and no external provider calls.
- Localizing internal relationship labels in iOS keeps the backend state contract stable while preventing technical IDs from leaking into the play surface.

## D070: Use an explicit launch storyboard before full page-turn UI

Reason:
- Real-device feedback showed that app startup could briefly show a black screen, which hurts the first playable impression before any richer UI transitions exist.
- A static launch storyboard gives iOS a stable warm background immediately while SwiftUI and backend loading start.
- This stays inside Phase 5 polish and does not introduce new navigation architecture, backend routes, model calls, or iOS secrets.

## D071: Lock the MVP brand to StoryCat by Station Cat

Reason:
- The product should now present as StoryCat / 故事猫 rather than the earlier working title Playable Novel.
- Keeping App Store titles, one-line introductions, launch copy, loading copy, and display name in one `AppBrand` constants layer reduces future naming drift.
- The brand lock is an iOS and documentation polish task only; it does not change backend routes, model providers, story contracts, payment scope, public sharing, or iOS secret handling.

## D072: Start page-turn UI as a client-only reading surface

Reason:
- The user wants the next round to feel like turning a page, but the current MVP should not risk a large navigation rewrite before real-device validation.
- A reusable SwiftUI `StoryBookPageView` gives the opening, latest turn, and reopened recent turns a paper-like reading surface while keeping choices, free text, feedback, caching, and backend routes unchanged.
- Showing a `正在翻页` overlay during turn requests and animating returned turns through a custom page transition makes the existing one-screen flow feel more novel-like without adding new APIs, model calls, or iOS secrets.

## D073: Replace the loaded iOS List with a custom bookshelf flow

Reason:
- Real-device feedback showed that the system List dark-mode styling made the paper page unreadable and also hid the page-turn effect inside list cells.
- A custom ScrollView-based bookshelf lets StoryCat show templates as books, cached stories as continue-reading books, and the selected template as a full-width book/role setup page.
- Forcing book pages and setup surfaces into a light paper color scheme with fixed dark ink preserves readability while keeping backend routes, API schemas, cache schemas, and provider behavior unchanged.

## D074: Remove fake-mode chapter-scene boilerplate from page copy

Reason:
- Real-device reading feedback showed the deterministic fake-mode suffix about `第 X 章的第 Y 幕`, `新的线索浮出水面`, and next-step pressure repeated on every story page and made the book UI feel templated.
- Fake mode should still be deterministic and varied, but story pages should show the player's action, protagonist response, and template-specific story beat without meta-style chapter/scene explanation inside the narrative body.
- This changes user-facing fake-mode narrative copy only; backend routes, response schemas, choice IDs, risk values, provider configuration, real-provider behavior, and iOS secret boundaries remain unchanged.

## D075: Pace story pages before choices

Reason:
- Real-device play feedback showed that very short turn text makes the app feel like a constant quiz instead of a living novel.
- Each returned story page should provide enough narrative texture, consequence, character/world reaction, and pressure before showing the next three choices.
- The MVP will keep the existing route shape with exactly three choices for now, but fake-mode copy and real-provider prompts should frame those choices as meaningful branch decisions at a key moment rather than tiny micro-actions.

## D076: Use chapter pacing stages for story quality tuning

Reason:
- Longer pages alone do not guarantee better story feel; each page needs a role inside the chapter.
- Phase 5 fake mode now treats chapter scenes as setup, pressure, reveal, or turning point so openings, turn narration, and choices feel less repetitive across multi-turn play.
- Choice labels should communicate different story functions: lower-risk investigation/holding action, medium-risk relationship or negotiation action, and higher-risk confrontation or breakthrough.
- Real-provider prompts receive the same pacing intent as request metadata/prompt payload, while the public API shape, choice IDs, risk values, provider-secret boundary, and iOS LLM-key boundary remain unchanged.

## D077: Use Cloudflare Workers plus KV for real-device backend validation

Reason:
- The user needs real-device testing without starting a local `uvicorn` backend or relying on a LAN IP.
- Cloudflare Python Workers can host the existing FastAPI route surface for the MVP fake-mode backend, but sync FastAPI endpoints must be async because the Workers runtime cannot start Python threadpool workers.
- Worker isolates do not provide durable in-memory story storage, so story records and per-device story indexes are persisted in Cloudflare KV for create, turn, resume, and list flows.
- This is a validation deployment, not the final production persistence design; real LLM secrets, payments, accounts, public sharing, and production-grade quotas remain out of this Phase 5 detour.

## D078: Use a custom-domain path for iOS validation

Reason:
- Real-device validation on mobile network reported timeout against a temporary validation hostname even though the Worker responded from the Mac.
- A project-owned custom domain can provide a more stable mobile-facing base URL than a temporary validation hostname.
- Registering the same FastAPI routers under `/storycat` keeps the internal route handlers and iOS request models unchanged while giving the app a stable custom-domain base URL.
- This remains a Phase 5 validation routing fix only; it does not add accounts, payments, public sharing, real LLM secrets, or a production persistence redesign.

## D079: Enter Phase 6 only after real-device and final closeout pass

Reason:
- Phase 5 required both user-led real-device validation and an automated final sweep before moving into safety, compliance, and TestFlight readiness.
- The Cloudflare custom-domain real-device checkpoint passed per user report on 2026-06-01.
- The final Phase 5 sweep passed with backend tests, iOS generic build, and `git diff --check`.
- Phase 6 may now start with lightweight safety/info surfaces and TestFlight readiness work, while payments, public sharing, creator marketplace, existing novel import, and Mainland China launch remain out of scope.
