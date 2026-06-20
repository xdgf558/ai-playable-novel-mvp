# StoryCat iOS App

The current iOS target still uses the internal Xcode project name `PlayableNovel`, while the user-facing product brand is StoryCat / 故事猫 by Station Cat.

## Backend

By default, `PlayableNovel/AppConfig.swift` points to the local backend:

```text
http://127.0.0.1:8000
```

Update that URL before testing against your own deployed backend.

## Open the Project

```bash
open ios/PlayableNovel.xcodeproj
```

## Build From the Command Line

```bash
xcodebuild \
  -project ios/PlayableNovel.xcodeproj \
  -scheme PlayableNovel \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  CODE_SIGNING_ALLOWED=NO \
  build
```

## Notes

- The app does not store any LLM API key on-device.
- Local simulator development is easiest when the backend runs at `http://127.0.0.1:8000`.
