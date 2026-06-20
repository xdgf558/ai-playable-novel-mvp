# StoryCat / 故事猫

StoryCat is an AI playable novel MVP by Station Cat.

It combines a FastAPI backend, a SwiftUI iOS app, and an optional Cloudflare Worker deployment path to explore long-form interactive storytelling for Chinese-first readers.

## 中文说明

StoryCat（故事猫）是一个由 Station Cat 打造的 AI 互动小说 MVP 项目。

这个仓库目前包含三部分：

- Python `FastAPI` 后端，用于故事生成、状态推进、接口返回和假数据模式开发
- SwiftUI iOS 客户端，用于模板选择、主角创建、剧情游玩和本地缓存
- 可选的 Cloudflare Worker 部署适配层，用于把同一套后端接口部署到边缘环境

项目当前更偏向一个可运行、可迭代、可继续扩展的原型版本，适合拿来研究：

- AI 互动叙事产品的基础架构
- iOS 客户端与后端 API 的协作方式
- 假数据模式到真实模型接入的演进路径
- 轻量级故事状态管理与多轮剧情推进

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
