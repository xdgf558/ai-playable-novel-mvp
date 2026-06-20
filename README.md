# StoryCat / 故事猫

StoryCat is an AI playable novel MVP by Station Cat.

It combines a FastAPI backend, a SwiftUI iOS app, and an optional Cloudflare Worker deployment path to explore long-form interactive storytelling for Chinese-first readers.

## Highlights

- AI playable novel flow with story templates, protagonist setup, branching turns, and persistent story state
- FastAPI backend with fake mode enabled by default for safe local development
- SwiftUI iOS client with local cache, anonymous device session bootstrap, and story continuation flow
- Optional Cloudflare Worker adapter for path-prefix deployments

## Tech Stack

- Backend: Python 3.12+, FastAPI, Pydantic v2
- iOS: SwiftUI, SwiftData, URLSession, Keychain
- Optional deployment: Cloudflare Python Workers + Cloudflare KV

## Repository Layout

- `app/`: backend API routes, services, schemas, and LLM integration layers
- `ios/`: SwiftUI iOS client
- `tests/`: backend test suite
- `worker.py`: Cloudflare Worker entrypoint for the FastAPI app
- `wrangler.jsonc`: safe deployment template without production identifiers

## Local Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

## Run Backend

```bash
uvicorn app.main:app --reload
```

Health check:

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Run Tests

```bash
pytest
```

## Open the iOS App

```bash
open ios/PlayableNovel.xcodeproj
```

Build from the command line:

```bash
xcodebuild \
  -project ios/PlayableNovel.xcodeproj \
  -scheme PlayableNovel \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  CODE_SIGNING_ALLOWED=NO \
  build
```

By default, `ios/PlayableNovel/AppConfig.swift` points to the local backend at `http://127.0.0.1:8000`. Update that value if you want the app to target your own deployed backend.

## Cloudflare Deployment Notes

`wrangler.jsonc` is checked in as a safe template. Before deploying, configure your own route, KV namespace, and environment values as needed for your setup.

## Security Notes

- Keep real provider credentials only in a local ignored `.env`
- Do not store LLM API keys in the iOS project
- Fake mode is the default safe configuration for local development

## Main Docs

- `API_CONTRACT.md`
- `ARCHITECTURE.md`
- `DECISIONS.md`
- `ios/README.md`
