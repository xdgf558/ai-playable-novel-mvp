import Foundation
import SwiftData

@Model
final class LocalStory {
    @Attribute(.unique) var storyID: String
    var title: String
    var templateID: String
    var locale: String
    var currentChapterIndex: Int
    var turnCount: Int
    var updatedAt: Date
    var stateJSON: String

    init(
        storyID: String,
        title: String,
        templateID: String,
        locale: String,
        currentChapterIndex: Int,
        turnCount: Int,
        updatedAt: Date,
        stateJSON: String
    ) {
        self.storyID = storyID
        self.title = title
        self.templateID = templateID
        self.locale = locale
        self.currentChapterIndex = currentChapterIndex
        self.turnCount = turnCount
        self.updatedAt = updatedAt
        self.stateJSON = stateJSON
    }
}

@Model
final class LocalTurn {
    @Attribute(.unique) var turnID: String
    var storyID: String
    var narrative: String
    var choicesJSON: String
    var createdAt: Date

    init(
        turnID: String,
        storyID: String,
        narrative: String,
        choicesJSON: String,
        createdAt: Date
    ) {
        self.turnID = turnID
        self.storyID = storyID
        self.narrative = narrative
        self.choicesJSON = choicesJSON
        self.createdAt = createdAt
    }
}

@MainActor
protocol StoryCaching {
    func upsertCreatedStory(
        _ story: CreateStoryResponse,
        templateID: String,
        locale: String
    ) throws
    func upsertPlayedTurn(_ turn: PlayTurnResponse) throws
    func cachedStory(storyID: UUID) throws -> LocalStory?
    func cachedTurn(turnID: UUID) throws -> LocalTurn?
}

enum StoryCacheError: Error {
    case invalidJSONEncoding
}

@MainActor
struct SwiftDataStoryCache: StoryCaching {
    private let modelContext: ModelContext

    init(modelContext: ModelContext) {
        self.modelContext = modelContext
    }

    func upsertCreatedStory(
        _ story: CreateStoryResponse,
        templateID: String,
        locale: String = AppConfig.defaultLocale
    ) throws {
        let stateJSON = try jsonString(from: story.currentState)
        let storyID = story.storyID.uuidString
        let cachedStory = try cachedStory(storyID: story.storyID)

        if let cachedStory {
            cachedStory.title = story.title
            cachedStory.templateID = story.currentState.stringValue(for: "template_id") ?? templateID
            cachedStory.locale = story.currentState.stringValue(for: "locale") ?? locale
            cachedStory.currentChapterIndex = story.currentState.intValue(for: "current_chapter_index") ?? 1
            cachedStory.turnCount = story.currentState.intValue(for: "turn_count") ?? 0
            cachedStory.updatedAt = story.currentState.dateValue(for: "updated_at") ?? Date()
            cachedStory.stateJSON = stateJSON
        } else {
            modelContext.insert(
                LocalStory(
                    storyID: storyID,
                    title: story.title,
                    templateID: story.currentState.stringValue(for: "template_id") ?? templateID,
                    locale: story.currentState.stringValue(for: "locale") ?? locale,
                    currentChapterIndex: story.currentState.intValue(for: "current_chapter_index") ?? 1,
                    turnCount: story.currentState.intValue(for: "turn_count") ?? 0,
                    updatedAt: story.currentState.dateValue(for: "updated_at") ?? Date(),
                    stateJSON: stateJSON
                )
            )
        }

        try modelContext.save()
    }

    func upsertPlayedTurn(_ turn: PlayTurnResponse) throws {
        let choicesJSON = try jsonString(from: turn.choices)
        let turnID = turn.turnID.uuidString
        let storyID = turn.storyID.uuidString
        let now = Date()

        if let cachedTurn = try cachedTurn(turnID: turn.turnID) {
            cachedTurn.storyID = storyID
            cachedTurn.narrative = turn.narrative
            cachedTurn.choicesJSON = choicesJSON
            cachedTurn.createdAt = now
        } else {
            modelContext.insert(
                LocalTurn(
                    turnID: turnID,
                    storyID: storyID,
                    narrative: turn.narrative,
                    choicesJSON: choicesJSON,
                    createdAt: now
                )
            )
        }

        if let cachedStory = try cachedStory(storyID: turn.storyID) {
            cachedStory.currentChapterIndex = turn.chapterProgress.currentChapterIndex
            cachedStory.turnCount = turn.state.intValue(for: "turn_count") ?? cachedStory.turnCount + 1
            cachedStory.updatedAt = turn.state.dateValue(for: "updated_at") ?? now
            cachedStory.stateJSON = try jsonString(from: turn.state)
        }

        try modelContext.save()
    }

    func cachedStory(storyID: UUID) throws -> LocalStory? {
        try modelContext.fetch(FetchDescriptor<LocalStory>())
            .first { $0.storyID == storyID.uuidString }
    }

    func cachedTurn(turnID: UUID) throws -> LocalTurn? {
        try modelContext.fetch(FetchDescriptor<LocalTurn>())
            .first { $0.turnID == turnID.uuidString }
    }

    private func jsonString<Value: Encodable>(from value: Value) throws -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(value)

        guard let string = String(data: data, encoding: .utf8) else {
            throw StoryCacheError.invalidJSONEncoding
        }

        return string
    }
}

private extension Dictionary where Key == String, Value == JSONValue {
    func intValue(for key: String) -> Int? {
        guard let value = self[key] else {
            return nil
        }

        if case .int(let intValue) = value {
            return intValue
        }

        return nil
    }

    func stringValue(for key: String) -> String? {
        guard let value = self[key] else {
            return nil
        }

        if case .string(let stringValue) = value {
            return stringValue
        }

        return nil
    }

    func dateValue(for key: String) -> Date? {
        guard let value = stringValue(for: key) else {
            return nil
        }

        return ISO8601DateFormatter().date(from: value)
    }
}
