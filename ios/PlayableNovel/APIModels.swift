import Foundation

enum JSONValue: Codable, Equatable, Sendable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()

        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Int.self) {
            self = .int(value)
        } else if let value = try? container.decode(Double.self) {
            self = .double(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value.")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()

        switch self {
        case .string(let value):
            try container.encode(value)
        case .int(let value):
            try container.encode(value)
        case .double(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }
}

struct APIErrorEnvelope: Decodable, Equatable {
    let error: APIErrorDetail
}

struct APIErrorDetail: Decodable, Equatable, Error {
    let code: String
    let message: String
    let details: [String: JSONValue]
}

struct DeviceSessionRequest: Encodable, Equatable {
    let deviceID: UUID
    let appVersion: String
    let locale: String

    enum CodingKeys: String, CodingKey {
        case deviceID = "device_id"
        case appVersion = "app_version"
        case locale
    }

    init(deviceID: UUID, appVersion: String = AppConfig.appVersion, locale: String = AppConfig.defaultLocale) {
        self.deviceID = deviceID
        self.appVersion = appVersion
        self.locale = locale
    }
}

struct DeviceSessionResponse: Decodable, Equatable {
    let userID: UUID
    let deviceID: UUID
    let dailyTurnLimit: Int
    let turnsUsedToday: Int

    enum CodingKeys: String, CodingKey {
        case userID = "user_id"
        case deviceID = "device_id"
        case dailyTurnLimit = "daily_turn_limit"
        case turnsUsedToday = "turns_used_today"
    }
}

struct StoryTemplate: Decodable, Equatable, Identifiable {
    let id: String
    let name: String
    let genre: String
    let shortDescription: String
    let tags: [String]
    let recommendedTone: [String]

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case genre
        case shortDescription = "short_description"
        case tags
        case recommendedTone = "recommended_tone"
    }
}

struct TemplatesResponse: Decodable, Equatable {
    let templates: [StoryTemplate]
}

enum ProtagonistAgeBand: String, Codable {
    case adult
}

struct ProtagonistProfile: Codable, Equatable {
    let name: String
    let pronouns: String
    let ageBand: ProtagonistAgeBand
    let personality: [String]
    let startingRole: String
    let mainGoal: String
    let specialAbility: String

    enum CodingKeys: String, CodingKey {
        case name
        case pronouns
        case ageBand = "age_band"
        case personality
        case startingRole = "starting_role"
        case mainGoal = "main_goal"
        case specialAbility = "special_ability"
    }

    init(
        name: String,
        pronouns: String,
        ageBand: ProtagonistAgeBand = .adult,
        personality: [String],
        startingRole: String,
        mainGoal: String,
        specialAbility: String
    ) {
        self.name = name
        self.pronouns = pronouns
        self.ageBand = ageBand
        self.personality = personality
        self.startingRole = startingRole
        self.mainGoal = mainGoal
        self.specialAbility = specialAbility
    }
}

enum ContentRating: String, Codable {
    case teen
}

struct CreateStoryRequest: Encodable, Equatable {
    let deviceID: UUID
    let templateID: String
    let locale: String
    let protagonist: ProtagonistProfile
    let tone: String
    let contentRating: ContentRating

    enum CodingKeys: String, CodingKey {
        case deviceID = "device_id"
        case templateID = "template_id"
        case locale
        case protagonist
        case tone
        case contentRating = "content_rating"
    }

    init(
        deviceID: UUID,
        templateID: String,
        locale: String = AppConfig.defaultLocale,
        protagonist: ProtagonistProfile,
        tone: String = "热血、悬念、成长",
        contentRating: ContentRating = .teen
    ) {
        self.deviceID = deviceID
        self.templateID = templateID
        self.locale = locale
        self.protagonist = protagonist
        self.tone = tone
        self.contentRating = contentRating
    }
}

enum StoryChoiceRisk: String, Codable {
    case low
    case medium
    case high
}

struct StoryChoice: Codable, Equatable, Identifiable {
    let id: String
    let label: String
    let risk: StoryChoiceRisk
}

struct CreateStoryResponse: Decodable, Equatable {
    let storyID: UUID
    let title: String
    let openingNarrative: String
    let currentState: [String: JSONValue]
    let choices: [StoryChoice]

    enum CodingKeys: String, CodingKey {
        case storyID = "story_id"
        case title
        case openingNarrative = "opening_narrative"
        case currentState = "current_state"
        case choices
    }
}

struct GetStoryResponse: Decodable, Equatable {
    let storyID: UUID
    let title: String
    let currentState: [String: JSONValue]
    let latestTurns: [[String: JSONValue]]

    enum CodingKeys: String, CodingKey {
        case storyID = "story_id"
        case title
        case currentState = "current_state"
        case latestTurns = "latest_turns"
    }
}

struct StorySummary: Decodable, Equatable, Identifiable {
    let storyID: UUID
    let title: String
    let templateID: String
    let currentChapterIndex: Int
    let turnCount: Int
    let updatedAt: String

    var id: UUID {
        storyID
    }

    enum CodingKeys: String, CodingKey {
        case storyID = "story_id"
        case title
        case templateID = "template_id"
        case currentChapterIndex = "current_chapter_index"
        case turnCount = "turn_count"
        case updatedAt = "updated_at"
    }
}

struct ListStoriesResponse: Decodable, Equatable {
    let stories: [StorySummary]
}

enum TurnInputType: String, Codable {
    case choice
    case freeText = "free_text"
}

struct PlayTurnRequest: Encodable, Equatable {
    let deviceID: UUID
    let inputType: TurnInputType
    let choiceID: String?
    let userText: String?

    enum CodingKeys: String, CodingKey {
        case deviceID = "device_id"
        case inputType = "input_type"
        case choiceID = "choice_id"
        case userText = "user_text"
    }

    static func choice(deviceID: UUID, choiceID: String) -> PlayTurnRequest {
        PlayTurnRequest(deviceID: deviceID, inputType: .choice, choiceID: choiceID, userText: nil)
    }

    static func freeText(deviceID: UUID, userText: String) -> PlayTurnRequest {
        PlayTurnRequest(deviceID: deviceID, inputType: .freeText, choiceID: nil, userText: userText)
    }
}

struct ChapterProgress: Decodable, Equatable {
    let currentChapterIndex: Int
    let currentSceneIndex: Int
    let progressPercent: Int

    enum CodingKeys: String, CodingKey {
        case currentChapterIndex = "current_chapter_index"
        case currentSceneIndex = "current_scene_index"
        case progressPercent = "progress_percent"
    }
}

struct TurnUsage: Decodable, Equatable {
    let inputTokens: Int
    let outputTokens: Int
    let model: String

    enum CodingKeys: String, CodingKey {
        case inputTokens = "input_tokens"
        case outputTokens = "output_tokens"
        case model
    }
}

struct PlayTurnResponse: Decodable, Equatable {
    let turnID: UUID
    let storyID: UUID
    let narrative: String
    let choices: [StoryChoice]
    let state: [String: JSONValue]
    let chapterProgress: ChapterProgress
    let usage: TurnUsage
    let warnings: [String]

    enum CodingKeys: String, CodingKey {
        case turnID = "turn_id"
        case storyID = "story_id"
        case narrative
        case choices
        case state
        case chapterProgress = "chapter_progress"
        case usage
        case warnings
    }
}

enum FeedbackRating: String, Codable {
    case thumbsUp = "thumbs_up"
    case thumbsDown = "thumbs_down"
    case neutral
}

struct FeedbackRequest: Encodable, Equatable {
    let deviceID: UUID
    let storyID: UUID
    let turnID: UUID?
    let rating: FeedbackRating
    let reason: String
    let freeText: String?

    enum CodingKeys: String, CodingKey {
        case deviceID = "device_id"
        case storyID = "story_id"
        case turnID = "turn_id"
        case rating
        case reason
        case freeText = "free_text"
    }
}

struct FeedbackResponse: Decodable, Equatable {
    let status: String
}
