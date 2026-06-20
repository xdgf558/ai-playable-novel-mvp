import Foundation
import SwiftData
import SwiftUI

protocol StoryCreating {
    func createStory(_ request: CreateStoryRequest) async throws -> CreateStoryResponse
}

extension APIClient: StoryCreating {}

protocol StoryFetching {
    func fetchStory(storyID: UUID) async throws -> GetStoryResponse
}

extension APIClient: StoryFetching {}

protocol TurnPlaying {
    func playTurn(storyID: UUID, request: PlayTurnRequest) async throws -> PlayTurnResponse
}

extension APIClient: TurnPlaying {}

protocol FeedbackSubmitting {
    func submitFeedback(_ request: FeedbackRequest) async throws -> FeedbackResponse
}

extension APIClient: FeedbackSubmitting {}

enum ProtagonistSetupField: String, CaseIterable {
    case name
    case pronouns
    case personality
    case startingRole
    case mainGoal
    case specialAbility
}

struct ProtagonistSetupValidationError: Identifiable, Equatable {
    let field: ProtagonistSetupField
    let message: String

    var id: String {
        field.rawValue
    }
}

struct ProtagonistSetupDraft: Equatable {
    var name = ""
    var pronouns = "他"
    var personality = ""
    var startingRole = ""
    var mainGoal = ""
    var specialAbility = ""
    var tone = "热血、悬念、成长"

    var validationErrors: [ProtagonistSetupValidationError] {
        var errors: [ProtagonistSetupValidationError] = []

        if trimmed(name).isEmpty {
            errors.append(ProtagonistSetupValidationError(field: .name, message: "请输入主角姓名。"))
        }

        if trimmed(pronouns).isEmpty {
            errors.append(ProtagonistSetupValidationError(field: .pronouns, message: "请选择主角称谓。"))
        }

        if personalityTraits.isEmpty {
            errors.append(ProtagonistSetupValidationError(field: .personality, message: "请输入至少一个性格关键词。"))
        }

        if trimmed(startingRole).isEmpty {
            errors.append(ProtagonistSetupValidationError(field: .startingRole, message: "请输入开局身份。"))
        }

        if trimmed(mainGoal).isEmpty {
            errors.append(ProtagonistSetupValidationError(field: .mainGoal, message: "请输入主线目标。"))
        }

        if trimmed(specialAbility).isEmpty {
            errors.append(ProtagonistSetupValidationError(field: .specialAbility, message: "请输入特殊能力。"))
        }

        return errors
    }

    var isValid: Bool {
        validationErrors.isEmpty
    }

    var personalityTraits: [String] {
        personality
            .split { character in
                character == "、" || character == "," || character == "，"
            }
            .map { trimmed(String($0)) }
            .filter { !$0.isEmpty }
    }

    var hasGeneratedSetup: Bool {
        !personalityTraits.isEmpty
            && !trimmed(startingRole).isEmpty
            && !trimmed(mainGoal).isEmpty
            && !trimmed(specialAbility).isEmpty
    }

    mutating func randomizeGeneratedSetup(for template: StoryTemplate) {
        let setup = ProtagonistSetupGenerator.randomSetup(for: template)
        personality = setup.personality.joined(separator: "、")
        startingRole = setup.startingRole
        mainGoal = setup.mainGoal
        specialAbility = setup.specialAbility
        tone = setup.tone
    }

    func makeCreateStoryRequest(
        deviceID: UUID,
        templateID: String,
        locale: String = AppConfig.defaultLocale
    ) -> CreateStoryRequest? {
        guard let profile = makeProtagonistProfile() else {
            return nil
        }

        return CreateStoryRequest(
            deviceID: deviceID,
            templateID: templateID,
            locale: locale,
            protagonist: profile,
            tone: trimmedTone
        )
    }

    func makeProtagonistProfile() -> ProtagonistProfile? {
        guard isValid else {
            return nil
        }

        return ProtagonistProfile(
            name: trimmed(name),
            pronouns: trimmed(pronouns),
            personality: personalityTraits,
            startingRole: trimmed(startingRole),
            mainGoal: trimmed(mainGoal),
            specialAbility: trimmed(specialAbility)
        )
    }

    private var trimmedTone: String {
        let value = trimmed(tone)
        return value.isEmpty ? "热血、悬念、成长" : value
    }

    private func trimmed(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

struct ProtagonistGeneratedSetup: Equatable {
    let personality: [String]
    let startingRole: String
    let mainGoal: String
    let specialAbility: String
    let tone: String
}

enum ProtagonistSetupGenerator {
    static func randomSetup(for template: StoryTemplate) -> ProtagonistGeneratedSetup {
        let pack = setupPack(for: template)

        return ProtagonistGeneratedSetup(
            personality: pack.personalities.randomElement() ?? ["冷静", "果断", "重情义"],
            startingRole: pack.startingRoles.randomElement() ?? "刚被卷入主线事件的普通人",
            mainGoal: pack.mainGoals.randomElement() ?? "找出真相并守住重要的人",
            specialAbility: pack.specialAbilities.randomElement() ?? "能在关键时刻捕捉细微线索",
            tone: tone(for: template)
        )
    }

    private static func tone(for template: StoryTemplate) -> String {
        if !template.recommendedTone.isEmpty {
            return template.recommendedTone.joined(separator: "、")
        }

        return "热血、悬念、成长"
    }

    private static func setupPack(for template: StoryTemplate) -> SetupPack {
        switch template.id {
        case "xianxia_rise":
            return SetupPack(
                personalities: [
                    ["坚韧", "敏锐", "重承诺"],
                    ["隐忍", "胆大", "护短"],
                    ["冷静", "好奇", "不服输"]
                ],
                startingRoles: [
                    "被外门低估的杂役弟子",
                    "替师门守夜的药圃学徒",
                    "刚捡到残缺玉简的山村少年"
                ],
                mainGoals: [
                    "查清师门禁地异动并争取入内门的机会",
                    "在宗门试炼前修复被毁的灵根名声",
                    "找到失踪亲人留下的修行线索"
                ],
                specialAbilities: [
                    "能听见古玉中残留的剑意回响",
                    "每次濒危时都能短暂看见灵气流向",
                    "可以从废丹残渣里辨认真正的药性"
                ]
            )

        case "apocalypse_base":
            return SetupPack(
                personalities: [
                    ["谨慎", "果断", "护短"],
                    ["务实", "冷静", "有担当"],
                    ["敏感", "机警", "不认命"]
                ],
                startingRoles: [
                    "废弃地铁站里的临时营地记录员",
                    "刚护送幸存者抵达基地的巡逻队新人",
                    "掌握附近物资路线的前快递员"
                ],
                mainGoals: [
                    "在下一次尸潮前让营地获得稳定水源",
                    "查清基地电台里反复出现的求救坐标",
                    "保护幸存者队伍穿过失控城区"
                ],
                specialAbilities: [
                    "能提前感知感染体集群的移动方向",
                    "可以快速修复旧设备并短暂增强功率",
                    "记得城市废墟中许多被忽略的备用通道"
                ]
            )

        case "urban_ability":
            return SetupPack(
                personalities: [
                    ["嘴硬", "细心", "正义感强"],
                    ["沉稳", "敏锐", "不轻信人"],
                    ["洒脱", "胆大", "重朋友"]
                ],
                startingRoles: [
                    "刚觉醒异常能力的夜班便利店店员",
                    "被卷入都市异能案件的实习记者",
                    "替朋友调查失踪案的普通大学生"
                ],
                mainGoals: [
                    "查清能力来源并阻止地下组织继续抓人",
                    "在城市暗线曝光前保护身边的人",
                    "找到同类留下的安全联络点"
                ],
                specialAbilities: [
                    "触碰物品时能看见十秒内的残留画面",
                    "在霓虹灯下能短暂放慢自己的体感时间",
                    "能听见谎言里不协调的心跳声"
                ]
            )

        case "infinity_trial":
            return SetupPack(
                personalities: [
                    ["冷静", "善观察", "敢赌"],
                    ["理性", "警惕", "保护欲强"],
                    ["敏锐", "克制", "不服输"]
                ],
                startingRoles: [
                    "刚醒在陌生试炼车厢里的新玩家",
                    "被系统误判为老手的普通上班族",
                    "唯一记得上一轮细节的失忆幸存者"
                ],
                mainGoals: [
                    "活过三场试炼并找到系统漏洞",
                    "带队友离开第一层规则迷宫",
                    "查清自己为什么被反复投放到同一关"
                ],
                specialAbilities: [
                    "能在规则文本里看见被隐藏的一行提示",
                    "每轮试炼开始前可保留一个微弱线索",
                    "能判断一次选择会触发低、中、高哪类风险"
                ]
            )

        case "detective_mystery":
            return SetupPack(
                personalities: [
                    ["冷静", "敏锐", "有同理心"],
                    ["寡言", "细致", "不放过矛盾"],
                    ["温和", "坚持", "擅长倾听"]
                ],
                startingRoles: [
                    "受邀重查旧案的民间顾问",
                    "刚接手密室案卷宗的年轻侦探",
                    "在暴雨山庄里发现第一处矛盾的客人"
                ],
                mainGoals: [
                    "在凶手再次行动前还原第一案发现场",
                    "找出每位嫌疑人都在隐瞒的关键时间线",
                    "破解遗留信件中指向真相的暗号"
                ],
                specialAbilities: [
                    "能从证词停顿中捕捉被刻意省略的信息",
                    "可以快速在脑中重建房间动线",
                    "对气味、纸张和细小划痕格外敏感"
                ]
            )

        default:
            return SetupPack(
                personalities: [
                    ["冷静", "敏锐", "重情义"],
                    ["果断", "好奇", "不服输"],
                    ["谨慎", "善观察", "有担当"]
                ],
                startingRoles: [
                    "刚踏入\(template.genre)事件中心的新人",
                    "被意外线索推到台前的普通人",
                    "与主线谜团有隐秘关联的见证者"
                ],
                mainGoals: [
                    "找出真相并完成自己的第一次逆转",
                    "保护重要的人，同时弄清事件背后的动机",
                    "在危机扩大前抓住唯一的破局机会"
                ],
                specialAbilities: [
                    "能在混乱场面中迅速抓住关键细节",
                    "可以把零散线索串成清晰判断",
                    "越到危险关头越能保持稳定行动"
                ]
            )
        }
    }

    private struct SetupPack {
        let personalities: [[String]]
        let startingRoles: [String]
        let mainGoals: [String]
        let specialAbilities: [String]
    }
}

enum StoryCreationState: Equatable {
    case idle
    case creating
    case created(CreateStoryResponse)
    case failed(String)
}

enum StoryTurnState: Equatable {
    case idle
    case playing
    case played(PlayTurnResponse)
    case failed(String)
}

enum CachedStoryOpenState: Equatable {
    case idle
    case opening(String)
    case opened(GetStoryResponse)
    case failed(String)
}

enum FeedbackSubmissionState: Equatable {
    case idle
    case submitting
    case submitted
    case failed(String)
}

enum ResumedStoryChoiceParser {
    static func choices(from latestTurns: [[String: JSONValue]]) -> [StoryChoice] {
        guard let latestTurn = latestTurns.last,
              case .array(let choiceValues) = latestTurn["choices"] else {
            return []
        }

        return choiceValues.compactMap(choice(from:))
    }

    private static func choice(from value: JSONValue) -> StoryChoice? {
        guard case .object(let object) = value,
              let id = stringValue(from: object, key: "id"),
              let label = stringValue(from: object, key: "label"),
              let riskRawValue = stringValue(from: object, key: "risk"),
              let risk = StoryChoiceRisk(rawValue: riskRawValue) else {
            return nil
        }

        return StoryChoice(id: id, label: label, risk: risk)
    }

    private static func stringValue(from object: [String: JSONValue], key: String) -> String? {
        guard let value = object[key],
              case .string(let stringValue) = value else {
            return nil
        }

        let trimmedValue = stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmedValue.isEmpty ? nil : trimmedValue
    }
}

struct StoryVisibleRelationship: Equatable, Identifiable {
    let id: String
    let affinity: Int?
    let trust: Int?
    let status: String?

    var summaryLine: String {
        var parts = [displayName]

        if let localizedStatus {
            parts.append(localizedStatus)
        }

        var scoreParts: [String] = []
        if let affinity {
            scoreParts.append("好感 \(affinity)")
        }
        if let trust {
            scoreParts.append("信任 \(trust)")
        }
        if !scoreParts.isEmpty {
            parts.append(scoreParts.joined(separator: " / "))
        }

        return parts.joined(separator: " · ")
    }

    private var displayName: String {
        switch id {
        case "npc_001":
            return "神秘引路人"
        default:
            if id.contains("_") {
                return "重要角色"
            }

            return id
        }
    }

    private var localizedStatus: String? {
        guard let status else {
            return nil
        }

        switch status {
        case "unknown":
            return nil
        case "watching":
            return "正在观察"
        case "testing":
            return "试探中"
        case "ally":
            return "可信任"
        case "hostile":
            return "有敌意"
        default:
            if status.contains("_") {
                return nil
            }

            return status
        }
    }
}

struct StoryVisibleInventoryItem: Equatable, Identifiable {
    let id: String
    let name: String
    let quantity: Int
    let description: String?

    var summaryLine: String {
        var line = "\(name) x\(quantity)"

        if let description {
            line += " · \(description)"
        }

        return line
    }
}

struct StoryVisibleStateSnapshot: Equatable {
    let relationships: [StoryVisibleRelationship]
    let inventory: [StoryVisibleInventoryItem]

    init(state: [String: JSONValue]) {
        relationships = Self.relationships(from: state)
        inventory = Self.inventory(from: state)
    }

    var summaryLines: [String] {
        let relationshipText: String
        if relationships.isEmpty {
            relationshipText = "关系：暂无"
        } else {
            relationshipText = "关系：" + relationships.map(\.summaryLine).joined(separator: "；")
        }

        let inventoryText: String
        if inventory.isEmpty {
            inventoryText = "物品：暂无"
        } else {
            inventoryText = "物品：" + inventory.map(\.summaryLine).joined(separator: "；")
        }

        return [relationshipText, inventoryText]
    }

    private static func relationships(from state: [String: JSONValue]) -> [StoryVisibleRelationship] {
        guard case .object(let relationshipValues) = state["relationships"] else {
            return []
        }

        return relationshipValues
            .compactMap { characterID, value -> StoryVisibleRelationship? in
                guard case .object(let object) = value else {
                    return nil
                }

                return StoryVisibleRelationship(
                    id: characterID,
                    affinity: intValue(from: object, key: "affinity"),
                    trust: intValue(from: object, key: "trust"),
                    status: stringValue(from: object, key: "status")
                )
            }
            .sorted { $0.id < $1.id }
    }

    private static func inventory(from state: [String: JSONValue]) -> [StoryVisibleInventoryItem] {
        guard case .array(let inventoryValues) = state["inventory"] else {
            return []
        }

        return inventoryValues.compactMap { value -> StoryVisibleInventoryItem? in
            guard case .object(let object) = value else {
                return nil
            }

            let id = stringValue(from: object, key: "id")
            let name = stringValue(from: object, key: "name")
            let displayName = name ?? id

            guard let itemID = id ?? name,
                  let displayName else {
                return nil
            }

            return StoryVisibleInventoryItem(
                id: itemID,
                name: displayName,
                quantity: intValue(from: object, key: "quantity") ?? 1,
                description: stringValue(from: object, key: "description")
            )
        }
    }

    private static func intValue(from object: [String: JSONValue], key: String) -> Int? {
        guard let value = object[key],
              case .int(let intValue) = value else {
            return nil
        }

        return intValue
    }

    private static func stringValue(from object: [String: JSONValue], key: String) -> String? {
        guard let value = object[key],
              case .string(let stringValue) = value else {
            return nil
        }

        let trimmedValue = stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmedValue.isEmpty ? nil : trimmedValue
    }
}

enum AIContentNoticeCopy {
    static let title = "AI 生成内容提示"
    static let message = "故事由 AI 辅助生成，可能不准确、重复或出乎预期。请勿输入受版权保护作品、隐私或违法内容。"
}

struct AIContentNoticeView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(AIContentNoticeCopy.title, systemImage: "sparkles")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)

            Text(AIContentNoticeCopy.message)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}

enum PlayableNovelStyle {
    static let gold = Color(red: 0.94, green: 0.58, blue: 0.18)
    static let teal = Color(red: 0.16, green: 0.68, blue: 0.62)
    static let danger = Color(red: 0.86, green: 0.27, blue: 0.22)

    static var screenBackground: LinearGradient {
        LinearGradient(
            colors: [
                Color(red: 0.98, green: 0.96, blue: 0.92),
                Color(red: 0.08, green: 0.12, blue: 0.14).opacity(0.18),
                Color(red: 0.28, green: 0.16, blue: 0.05).opacity(0.10)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

struct LoadingStateView: View {
    var body: some View {
        VStack(spacing: 18) {
            ZStack {
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color(red: 0.12, green: 0.18, blue: 0.16))
                    .frame(width: 64, height: 64)
                    .shadow(color: .black.opacity(0.10), radius: 18, y: 10)

                Image(systemName: "book.pages.fill")
                    .font(.system(size: 30, weight: .semibold))
                    .foregroundStyle(Color(red: 0.98, green: 0.96, blue: 0.92))
            }

            VStack(spacing: 6) {
                Text(AppBrand.productName)
                    .font(.largeTitle.weight(.bold))
                    .foregroundStyle(Color(red: 0.12, green: 0.18, blue: 0.16))

                Text(AppBrand.chineseName)
                    .font(.headline.weight(.semibold))
                    .foregroundStyle(.primary)

                Text(AppBrand.stationCatByline)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)

                Text(AppBrand.loadingMessage)
                    .font(.headline)
                    .foregroundStyle(PlayableNovelStyle.teal)
            }

            ProgressView()
                .controlSize(.regular)
                .tint(PlayableNovelStyle.teal)

            Text(AppBrand.connectionMessage)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(PlayableNovelStyle.screenBackground.ignoresSafeArea())
    }
}

struct PlaceholderStateView: View {
    let systemImage: String
    let title: String
    let message: String
    let buttonTitle: String
    let action: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Image(systemName: systemImage)
                .font(.system(size: 44, weight: .semibold))
                .foregroundStyle(PlayableNovelStyle.gold)

            VStack(alignment: .leading, spacing: 8) {
                Text(title)
                    .font(.title2.weight(.bold))

                Text(message)
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Button(action: action) {
                Label(buttonTitle, systemImage: "arrow.clockwise")
            }
            .buttonStyle(.borderedProminent)

            Spacer()
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(PlayableNovelStyle.screenBackground.ignoresSafeArea())
    }
}

struct SessionSummaryView: View {
    let session: DeviceSessionState

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(PlayableNovelStyle.gold.opacity(0.18))
                        .frame(width: 44, height: 44)

                    Image(systemName: "book.pages.fill")
                        .font(.title3)
                        .foregroundStyle(PlayableNovelStyle.gold)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("\(AppBrand.productName) \(AppBrand.chineseName)")
                        .font(.title3.weight(.bold))

                    Text(AppBrand.stationCatByline)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(PlayableNovelStyle.teal)

                    Text(AppBrand.taglineChinese)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)

                    Text("今日回合 \(session.turnsUsedToday) / \(session.dailyTurnLimit)")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Spacer()
            }

            ProgressView(value: progressValue)
                .tint(PlayableNovelStyle.teal)
        }
        .padding(.vertical, 8)
    }

    private var progressValue: Double {
        guard session.dailyTurnLimit > 0 else {
            return 0
        }

        return min(Double(session.turnsUsedToday) / Double(session.dailyTurnLimit), 1)
    }
}

struct TemplateRowView: View {
    let template: StoryTemplate
    let isSelected: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(template.name)
                        .font(.headline)

                    Text(template.genre)
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(PlayableNovelStyle.teal.opacity(0.14), in: Capsule())
                        .foregroundStyle(PlayableNovelStyle.teal)

                    Spacer(minLength: 0)
                }

                Text(template.shortDescription)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                if !template.tags.isEmpty {
                    Text(template.tags.joined(separator: " / "))
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }

            if isSelected {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(PlayableNovelStyle.gold)
                    .imageScale(.large)
                    .accessibilityLabel("已选择")
            }
        }
        .padding(.vertical, 6)
    }
}

struct StoryHomePanel<Content: View>: View {
    let title: String
    let subtitle: String?
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.title3.weight(.bold))
                    .foregroundStyle(Color(red: 0.10, green: 0.13, blue: 0.12))

                if let subtitle {
                    Text(subtitle)
                        .font(.subheadline)
                        .foregroundStyle(Color(red: 0.33, green: 0.29, blue: 0.23))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            content
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(Color(red: 0.98, green: 0.95, blue: 0.88).opacity(0.96))
                .overlay(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .stroke(Color(red: 0.49, green: 0.32, blue: 0.13).opacity(0.16), lineWidth: 1)
                )
        )
        .shadow(color: .black.opacity(0.08), radius: 14, y: 8)
        .environment(\.colorScheme, .light)
    }
}

struct StoryTemplateBookshelfView: View {
    let templates: [StoryTemplate]
    let onSelect: (StoryTemplate) -> Void

    private let columns = [
        GridItem(.flexible(), spacing: 14),
        GridItem(.flexible(), spacing: 14)
    ]

    var body: some View {
        StoryHomePanel(
            title: "故事书架",
            subtitle: "从书架上取下一本书，再创建你的主角。"
        ) {
            LazyVGrid(columns: columns, spacing: 14) {
                ForEach(templates) { template in
                    Button {
                        onSelect(template)
                    } label: {
                        StoryBookCoverView(template: template)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

struct StoryBookCoverView: View {
    let template: StoryTemplate

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                Rectangle()
                    .fill(Color.white.opacity(0.36))
                    .frame(width: 7)
                    .clipShape(Capsule())

                Spacer()

                Text(template.genre)
                    .font(.caption.weight(.bold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.white.opacity(0.22), in: Capsule())
            }

            Spacer(minLength: 10)

            Text(template.name)
                .font(.headline.weight(.bold))
                .lineLimit(2)
                .minimumScaleFactor(0.82)

            Text(template.shortDescription)
                .font(.caption)
                .lineLimit(4)
                .fixedSize(horizontal: false, vertical: true)

            Spacer(minLength: 8)

            if !template.tags.isEmpty {
                Text(template.tags.prefix(3).joined(separator: " · "))
                    .font(.caption2.weight(.semibold))
                    .lineLimit(1)
                    .foregroundStyle(.white.opacity(0.78))
            }
        }
        .foregroundStyle(.white)
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 210, alignment: .leading)
        .background(coverGradient, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(alignment: .leading) {
            Rectangle()
                .fill(Color.black.opacity(0.18))
                .frame(width: 12)
                .clipShape(UnevenRoundedRectangle(
                    topLeadingRadius: 8,
                    bottomLeadingRadius: 8
                ))
        }
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(Color.white.opacity(0.16), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.18), radius: 10, x: 0, y: 8)
    }

    private var coverGradient: LinearGradient {
        let colors: [Color]

        switch template.id {
        case "xianxia_rise":
            colors = [Color(red: 0.12, green: 0.44, blue: 0.40), Color(red: 0.68, green: 0.42, blue: 0.12)]
        case "apocalypse_base":
            colors = [Color(red: 0.31, green: 0.11, blue: 0.12), Color(red: 0.75, green: 0.32, blue: 0.13)]
        case "urban_ability":
            colors = [Color(red: 0.10, green: 0.20, blue: 0.42), Color(red: 0.16, green: 0.66, blue: 0.70)]
        case "infinity_trial":
            colors = [Color(red: 0.14, green: 0.12, blue: 0.25), Color(red: 0.54, green: 0.42, blue: 0.82)]
        case "detective_mystery":
            colors = [Color(red: 0.20, green: 0.16, blue: 0.12), Color(red: 0.63, green: 0.47, blue: 0.28)]
        default:
            colors = [Color(red: 0.12, green: 0.18, blue: 0.16), PlayableNovelStyle.teal]
        }

        return LinearGradient(colors: colors, startPoint: .topLeading, endPoint: .bottomTrailing)
    }
}

struct CachedStoryBookshelfView: View {
    let stories: [LocalStory]
    let loadingStoryID: String?
    let isOpening: Bool
    let onOpen: (LocalStory) -> Void

    var body: some View {
        StoryHomePanel(
            title: "继续阅读",
            subtitle: "从上次放回书架的位置继续。"
        ) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 12) {
                    ForEach(stories, id: \.storyID) { story in
                        Button {
                            onOpen(story)
                        } label: {
                            CachedStoryBookCoverView(
                                story: story,
                                isLoading: loadingStoryID == story.storyID
                            )
                        }
                        .buttonStyle(.plain)
                        .disabled(isOpening)
                    }
                }
                .padding(.vertical, 2)
            }
        }
    }
}

struct CachedStoryBookCoverView: View {
    let story: LocalStory
    let isLoading: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "book.closed.fill")
                    .foregroundStyle(PlayableNovelStyle.gold)

                Spacer()

                if isLoading {
                    ProgressView()
                        .controlSize(.small)
                        .tint(PlayableNovelStyle.teal)
                }
            }

            Text(story.title)
                .font(.headline.weight(.bold))
                .foregroundStyle(Color(red: 0.10, green: 0.13, blue: 0.12))
                .lineLimit(2)

            Text("第 \(story.currentChapterIndex) 章 · \(story.turnCount) 回合")
                .font(.caption.weight(.semibold))
                .foregroundStyle(PlayableNovelStyle.teal)

            Text(story.updatedAt.formatted(date: .abbreviated, time: .shortened))
                .font(.caption2)
                .foregroundStyle(Color(red: 0.34, green: 0.29, blue: 0.22))
        }
        .padding(14)
        .frame(width: 170, height: 170, alignment: .leading)
        .background(
            LinearGradient(
                colors: [
                    Color(red: 0.99, green: 0.95, blue: 0.83),
                    Color(red: 0.90, green: 0.78, blue: 0.56)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 8, style: .continuous)
        )
        .overlay(alignment: .leading) {
            Rectangle()
                .fill(Color.black.opacity(0.12))
                .frame(width: 10)
                .clipShape(UnevenRoundedRectangle(topLeadingRadius: 8, bottomLeadingRadius: 8))
        }
        .shadow(color: .black.opacity(0.12), radius: 10, x: 0, y: 7)
    }
}

struct SelectedStoryBookSetupView: View {
    let template: StoryTemplate
    @Binding var draft: ProtagonistSetupDraft
    let didValidate: Bool
    let isCreating: Bool
    let failureMessage: String?
    let onShuffle: () -> Void
    let onStart: () -> Void
    let onBack: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Button(action: onBack) {
                    Label("返回书架", systemImage: "books.vertical")
                }
                .buttonStyle(.bordered)

                Spacer()
            }

            VStack(alignment: .leading, spacing: 18) {
                StoryBookCoverView(template: template)
                    .frame(maxWidth: 240)

                VStack(alignment: .leading, spacing: 8) {
                    Text("角色页")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(PlayableNovelStyle.teal)

                    Text("为《\(template.name)》创建主角")
                        .font(.title2.weight(.bold))
                        .foregroundStyle(Color(red: 0.10, green: 0.13, blue: 0.12))
                        .fixedSize(horizontal: false, vertical: true)

                    Text("你只需要输入姓名和称谓，其余设定会随机生成。")
                        .font(.subheadline)
                        .foregroundStyle(Color(red: 0.34, green: 0.29, blue: 0.22))
                }

                VStack(alignment: .leading, spacing: 12) {
                    TextField("主角姓名", text: $draft.name)
                        .textFieldStyle(.roundedBorder)
                        .foregroundStyle(Color(red: 0.10, green: 0.13, blue: 0.12))

                    Picker("称谓", selection: $draft.pronouns) {
                        Text("他").tag("他")
                        Text("她").tag("她")
                        Text("TA").tag("TA")
                    }
                    .pickerStyle(.segmented)

                    GeneratedSetupSummaryView(draft: draft)

                    HStack(spacing: 10) {
                        Button(action: onShuffle) {
                            Label("换一组", systemImage: "shuffle")
                        }
                        .buttonStyle(.bordered)

                        Button(action: onStart) {
                            if isCreating {
                                HStack(spacing: 8) {
                                    ProgressView()
                                    Text("翻开中")
                                }
                            } else {
                                Label("翻开故事", systemImage: "book.pages.fill")
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isCreating)
                    }
                }

                validationContent
            }
            .padding(20)
            .frame(maxWidth: .infinity, minHeight: 620, alignment: .topLeading)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Color(red: 1.00, green: 0.97, blue: 0.90))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .stroke(Color(red: 0.49, green: 0.32, blue: 0.13).opacity(0.18), lineWidth: 1)
                    )
            )
            .overlay(alignment: .trailing) {
                Rectangle()
                    .fill(Color.black.opacity(0.06))
                    .frame(width: 9)
                    .padding(.vertical, 10)
            }
            .shadow(color: .black.opacity(0.13), radius: 18, y: 10)
        }
        .environment(\.colorScheme, .light)
    }

    @ViewBuilder
    private var validationContent: some View {
        if didValidate {
            if let profile = draft.makeProtagonistProfile() {
                Label("\(profile.name) 可以进入故事。", systemImage: "checkmark.circle.fill")
                    .font(.subheadline)
                    .foregroundStyle(.green)
            } else {
                ForEach(draft.validationErrors) { error in
                    Label(error.message, systemImage: "exclamationmark.triangle.fill")
                        .font(.subheadline)
                        .foregroundStyle(.red)
                }
            }
        }

        if let failureMessage {
            Label(failureMessage, systemImage: "exclamationmark.triangle.fill")
                .font(.subheadline)
                .foregroundStyle(.red)
        }
    }
}

struct GeneratedSetupSummaryView: View {
    let draft: ProtagonistSetupDraft

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            GeneratedSetupLine(
                systemImage: "person.text.rectangle",
                title: "性格",
                value: draft.personalityTraits.joined(separator: "、")
            )
            GeneratedSetupLine(
                systemImage: "flag.checkered",
                title: "开局",
                value: draft.startingRole
            )
            GeneratedSetupLine(
                systemImage: "scope",
                title: "目标",
                value: draft.mainGoal
            )
            GeneratedSetupLine(
                systemImage: "sparkles",
                title: "能力",
                value: draft.specialAbility
            )
        }
        .padding(.vertical, 6)
    }
}

struct GeneratedSetupLine: View {
    let systemImage: String
    let title: String
    let value: String

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(PlayableNovelStyle.gold)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)

                Text(value.isEmpty ? "待生成" : value)
                    .font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

struct NarrativeBlockView: View {
    let title: String?
    let narrative: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let title {
                Text(title)
                    .font(.headline)
            }

            Text(narrative)
                .font(.body)
                .lineSpacing(3)
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 6)
    }
}

struct StoryBookPageView: View {
    let pageLabel: String
    let title: String?
    let narrative: String
    let progressText: String?
    let progressValue: Double?
    let stateLines: [String]
    let isTurning: Bool

    var body: some View {
        ZStack(alignment: .topTrailing) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .firstTextBaseline) {
                    Text(pageLabel)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(PlayableNovelStyle.teal)

                    Spacer(minLength: 12)

                    Text(AppBrand.productName)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(bookMutedText.opacity(0.60))
                }

                Divider()
                    .overlay(bookMutedText.opacity(0.22))

                if let title {
                    Text(title)
                        .font(.title3.weight(.bold))
                        .foregroundStyle(bookInk)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Text(narrative)
                    .font(.body)
                    .lineSpacing(6)
                    .foregroundStyle(bookInk)
                    .fixedSize(horizontal: false, vertical: true)

                if let progressText {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(progressText)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(bookMutedText)

                        if let progressValue {
                            ProgressView(value: progressValue)
                                .tint(PlayableNovelStyle.teal)
                        }
                    }
                    .padding(.top, 4)
                }

                if !stateLines.isEmpty {
                    Divider()
                        .overlay(bookMutedText.opacity(0.18))

                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(stateLines, id: \.self) { line in
                            Label(line, systemImage: "bookmark.fill")
                                .font(.caption)
                                .foregroundStyle(bookMutedText)
                        }
                    }
                }

                HStack {
                    Spacer()

                    Text(AppBrand.stationCatByline)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(bookMutedText.opacity(0.58))
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity, minHeight: 520, alignment: .topLeading)
            .background(pageBackground)
            .overlay(alignment: .trailing) {
                Rectangle()
                    .fill(pageEdgeGradient)
                    .frame(width: 7)
                    .padding(.vertical, 9)
            }
            .overlay(alignment: .topTrailing) {
                BookPageCornerFold()
            }
            .shadow(color: .black.opacity(0.10), radius: 18, x: 0, y: 10)
            .rotation3DEffect(
                .degrees(isTurning ? -4 : 0),
                axis: (x: 0, y: 1, z: 0),
                anchor: .leading,
                perspective: 0.55
            )

            if isTurning {
                BookPageFlipSheet()
                    .transition(.asymmetric(
                        insertion: .move(edge: .trailing).combined(with: .opacity),
                        removal: .move(edge: .leading).combined(with: .opacity)
                    ))

                BookPageTurnOverlay()
                    .transition(.opacity.combined(with: .scale(scale: 0.96)))
                    .padding(18)
            }
        }
        .animation(.easeInOut(duration: 0.22), value: isTurning)
        .environment(\.colorScheme, .light)
    }

    private var pageBackground: some View {
        RoundedRectangle(cornerRadius: 8, style: .continuous)
            .fill(
                LinearGradient(
                    colors: [
                        Color(red: 1.00, green: 0.98, blue: 0.93),
                        Color(red: 0.96, green: 0.92, blue: 0.84)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .overlay {
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(Color(red: 0.48, green: 0.32, blue: 0.14).opacity(0.16), lineWidth: 1)
            }
    }

    private var pageEdgeGradient: LinearGradient {
        LinearGradient(
            colors: [
                Color.black.opacity(0.05),
                Color.white.opacity(0.30),
                Color.black.opacity(0.08)
            ],
            startPoint: .leading,
            endPoint: .trailing
        )
    }

    private var bookInk: Color {
        Color(red: 0.10, green: 0.13, blue: 0.12)
    }

    private var bookMutedText: Color {
        Color(red: 0.34, green: 0.29, blue: 0.22)
    }
}

struct BookPageCornerFold: View {
    var body: some View {
        Path { path in
            path.move(to: CGPoint(x: 38, y: 0))
            path.addLine(to: CGPoint(x: 38, y: 38))
            path.addLine(to: CGPoint(x: 0, y: 0))
            path.closeSubpath()
        }
        .fill(
            LinearGradient(
                colors: [
                    Color.white.opacity(0.55),
                    Color(red: 0.86, green: 0.79, blue: 0.66).opacity(0.35)
                ],
                startPoint: .topTrailing,
                endPoint: .bottomLeading
            )
        )
        .frame(width: 38, height: 38)
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .accessibilityHidden(true)
    }
}

struct BookPageFlipSheet: View {
    var body: some View {
        HStack {
            Spacer(minLength: 0)

            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Color.white.opacity(0.76),
                            Color(red: 0.96, green: 0.90, blue: 0.78).opacity(0.82),
                            Color.white.opacity(0.38)
                        ],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .overlay(alignment: .leading) {
                    LinearGradient(
                        colors: [
                            Color.black.opacity(0.22),
                            Color.clear
                        ],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                    .frame(width: 24)
                }
                .frame(maxWidth: 210)
                .rotation3DEffect(
                    .degrees(-34),
                    axis: (x: 0, y: 1, z: 0),
                    anchor: .leading,
                    perspective: 0.72
                )
                .shadow(color: .black.opacity(0.18), radius: 18, x: -8, y: 8)
        }
        .padding(12)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

struct BookPageTurnOverlay: View {
    var body: some View {
        HStack(spacing: 8) {
            ProgressView()
                .controlSize(.small)
                .tint(PlayableNovelStyle.teal)

            Text("正在翻页")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Color(red: 0.12, green: 0.18, blue: 0.16))
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.ultraThinMaterial, in: Capsule())
        .overlay(
            Capsule()
                .stroke(PlayableNovelStyle.teal.opacity(0.18), lineWidth: 1)
        )
    }
}

private struct BookPageTurnTransitionModifier: ViewModifier {
    let angle: Double
    let offset: CGFloat
    let opacity: Double

    func body(content: Content) -> some View {
        content
            .opacity(opacity)
            .offset(x: offset)
            .rotation3DEffect(
                .degrees(angle),
                axis: (x: 0, y: 1, z: 0),
                anchor: offset >= 0 ? .leading : .trailing,
                perspective: 0.55
            )
    }
}

extension AnyTransition {
    static var bookPageTurn: AnyTransition {
        .asymmetric(
            insertion: .modifier(
                active: BookPageTurnTransitionModifier(angle: -16, offset: 54, opacity: 0),
                identity: BookPageTurnTransitionModifier(angle: 0, offset: 0, opacity: 1)
            ),
            removal: .modifier(
                active: BookPageTurnTransitionModifier(angle: 14, offset: -34, opacity: 0),
                identity: BookPageTurnTransitionModifier(angle: 0, offset: 0, opacity: 1)
            )
        )
    }
}

struct ChoiceButtonRow: View {
    let choice: StoryChoice
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(alignment: .center, spacing: 12) {
                Image(systemName: "arrow.turn.down.right")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(PlayableNovelStyle.teal)
                    .frame(width: 22)

                VStack(alignment: .leading, spacing: 5) {
                    Text(choice.label)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.primary)
                        .fixedSize(horizontal: false, vertical: true)

                    Text(riskLabel)
                        .font(.caption.weight(.medium))
                        .foregroundStyle(riskColor)
                }

                Spacer(minLength: 0)
            }
            .padding(.vertical, 8)
        }
        .buttonStyle(.plain)
    }

    private var riskLabel: String {
        switch choice.risk {
        case .low:
            return "低风险"
        case .medium:
            return "中风险"
        case .high:
            return "高风险"
        }
    }

    private var riskColor: Color {
        switch choice.risk {
        case .low:
            return PlayableNovelStyle.teal
        case .medium:
            return PlayableNovelStyle.gold
        case .high:
            return PlayableNovelStyle.danger
        }
    }
}

@MainActor
struct ContentView: View {
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \LocalStory.updatedAt, order: .reverse) private var cachedStories: [LocalStory]
    @StateObject private var viewModel: LaunchHomeViewModel
    @State private var selectedTemplateID: String?
    @State private var protagonistDraft = ProtagonistSetupDraft()
    @State private var didValidateProtagonist = false
    @State private var storyCreationState = StoryCreationState.idle
    @State private var storyTurnState = StoryTurnState.idle
    @State private var latestPlayedTurn: PlayTurnResponse?
    @State private var cachedStoryOpenState = CachedStoryOpenState.idle
    @State private var freeTextTurnInput = ""
    @State private var feedbackSubmissionState = FeedbackSubmissionState.idle
    @State private var feedbackReason = ""

    private let storyClient: any StoryCreating
    private let storyReader: any StoryFetching
    private let turnClient: any TurnPlaying
    private let feedbackClient: any FeedbackSubmitting
    private let storyCache: (any StoryCaching)?

    init() {
        _viewModel = StateObject(wrappedValue: LaunchHomeViewModel())
        let apiClient = APIClient()
        storyClient = apiClient
        storyReader = apiClient
        turnClient = apiClient
        feedbackClient = apiClient
        storyCache = nil
    }

    init(
        viewModel: LaunchHomeViewModel,
        storyClient: any StoryCreating = APIClient(),
        storyReader: any StoryFetching = APIClient(),
        turnClient: any TurnPlaying = APIClient(),
        feedbackClient: any FeedbackSubmitting = APIClient(),
        storyCache: (any StoryCaching)? = nil
    ) {
        _viewModel = StateObject(wrappedValue: viewModel)
        self.storyClient = storyClient
        self.storyReader = storyReader
        self.turnClient = turnClient
        self.feedbackClient = feedbackClient
        self.storyCache = storyCache
    }

    var body: some View {
        ZStack {
            PlayableNovelStyle.screenBackground
                .ignoresSafeArea()

            NavigationStack {
                content
                    .navigationTitle(AppBrand.productName)
                    .task {
                        if case .idle = viewModel.state {
                            await viewModel.load()
                        }
                    }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        switch viewModel.state {
        case .idle, .loading:
            LoadingStateView()

        case .failed(let errorState):
            PlaceholderStateView(
                systemImage: "wifi.slash",
                title: "连接失败",
                message: errorState.message,
                buttonTitle: "重试"
            ) {
                Task {
                    await viewModel.retry()
                }
            }

        case .loaded(let session, let templates):
            loadedContent(session: session, templates: templates)
        }
    }

    private func loadedContent(session: DeviceSessionState, templates: [StoryTemplate]) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if hasActiveStoryPage {
                    storyPlayContent(session: session)
                } else if hasOpenedCachedStory {
                    cachedStoryOpenContent(session: session)
                } else if let selectedTemplate = templates.first(where: { $0.id == selectedTemplateID }) {
                    selectedBookSetupContent(session: session, template: selectedTemplate)
                } else {
                    bookshelfHomeContent(session: session, templates: templates)
                }
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 14)
        }
        .background(PlayableNovelStyle.screenBackground.ignoresSafeArea())
        .tint(PlayableNovelStyle.teal)
    }

    @ViewBuilder
    private func bookshelfHomeContent(session: DeviceSessionState, templates: [StoryTemplate]) -> some View {
        StoryHomePanel(title: "StoryCat 书房", subtitle: AppBrand.taglineChinese) {
            SessionSummaryView(session: session)

            Divider()
                .overlay(Color.black.opacity(0.12))

            AIContentNoticeView()
        }

        if !cachedStories.isEmpty {
            CachedStoryBookshelfView(
                stories: cachedStories,
                loadingStoryID: loadingCachedStoryID,
                isOpening: isOpeningCachedStory
            ) { story in
                Task {
                    await openCachedStory(story)
                }
            }
        }

        StoryTemplateBookshelfView(templates: templates) { template in
            withAnimation(.easeInOut(duration: 0.28)) {
                selectedTemplateID = template.id
                protagonistDraft.randomizeGeneratedSetup(for: template)
                didValidateProtagonist = false
                storyCreationState = .idle
                storyTurnState = .idle
                cachedStoryOpenState = .idle
                latestPlayedTurn = nil
                freeTextTurnInput = ""
                resetFeedbackDraft()
            }
        }
    }

    private func selectedBookSetupContent(
        session: DeviceSessionState,
        template: StoryTemplate
    ) -> some View {
        SelectedStoryBookSetupView(
            template: template,
            draft: $protagonistDraft,
            didValidate: didValidateProtagonist,
            isCreating: isCreatingStory,
            failureMessage: storyCreationFailureMessage
        ) {
            protagonistDraft.randomizeGeneratedSetup(for: template)
            didValidateProtagonist = false
        } onStart: {
            Task {
                await createStory(session: session, template: template)
            }
        } onBack: {
            withAnimation(.easeInOut(duration: 0.24)) {
                selectedTemplateID = nil
                storyCreationState = .idle
                storyTurnState = .idle
                latestPlayedTurn = nil
                freeTextTurnInput = ""
                resetFeedbackDraft()
            }
        }
        .onAppear {
            if !protagonistDraft.hasGeneratedSetup {
                protagonistDraft.randomizeGeneratedSetup(for: template)
            }
        }
    }

    @ViewBuilder
    private func storyPlayContent(session: DeviceSessionState) -> some View {
        if case .created(let story) = storyCreationState, latestPlayedTurn == nil {
            VStack(alignment: .leading, spacing: 16) {
                StoryBookPageView(
                    pageLabel: "扉页",
                    title: story.title,
                    narrative: story.openingNarrative,
                    progressText: "故事开场",
                    progressValue: 0.03,
                    stateLines: openingStateSummaryLines(for: story.currentState),
                    isTurning: isPlayingTurn
                )
                .id("opening-\(story.storyID.uuidString)")
                .transition(.bookPageTurn)

                StoryHomePanel(title: "选择下一页", subtitle: "选择会推动故事继续翻页。") {
                    if !story.choices.isEmpty {
                        ForEach(story.choices) { choice in
                            ChoiceButtonRow(choice: choice) {
                                Task {
                                    await playSuggestedChoice(session: session, story: story, choice: choice)
                                }
                            }
                            .disabled(isPlayingTurn)
                        }
                    }

                    TextField("自由行动", text: $freeTextTurnInput, axis: .vertical)
                        .lineLimit(2...4)
                        .textFieldStyle(.roundedBorder)
                        .disabled(isPlayingTurn)

                    Button {
                        Task {
                            await playFreeTextTurn(session: session, storyID: story.storyID)
                        }
                    } label: {
                        Label("提交行动", systemImage: "paperplane.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!canSubmitFreeTextTurn)

                    turnStatusContent(loadingText: "正在翻到下一页...")
                }
            }
        }

        if let turn = latestPlayedTurn {
            VStack(alignment: .leading, spacing: 16) {
                let visibleState = StoryVisibleStateSnapshot(state: turn.state)

                StoryBookPageView(
                    pageLabel: latestTurnPageLabel(for: turn),
                    title: nil,
                    narrative: turn.narrative,
                    progressText: latestTurnProgressText(for: turn),
                    progressValue: latestTurnProgressValue(for: turn),
                    stateLines: visibleState.summaryLines,
                    isTurning: isPlayingTurn
                )
                .id(turn.turnID.uuidString)
                .transition(.bookPageTurn)

                StoryHomePanel(title: "继续翻页", subtitle: "选择一个方向，或写下你的行动。") {
                    if !turn.choices.isEmpty {
                        ForEach(turn.choices) { choice in
                            ChoiceButtonRow(choice: choice) {
                                Task {
                                    await playLatestTurnSuggestedChoice(
                                        session: session,
                                        turn: turn,
                                        choice: choice
                                    )
                                }
                            }
                            .disabled(isPlayingTurn)
                        }
                    }

                    TextField("继续行动", text: $freeTextTurnInput, axis: .vertical)
                        .lineLimit(2...4)
                        .textFieldStyle(.roundedBorder)
                        .disabled(isPlayingTurn)

                    Button {
                        Task {
                            await playFreeTextTurn(session: session, storyID: turn.storyID)
                        }
                    } label: {
                        Label("提交行动", systemImage: "paperplane.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!canSubmitFreeTextTurn)

                    turnStatusContent(loadingText: "正在翻到下一回合...")
                }

                StoryHomePanel(title: "反馈", subtitle: "告诉我们这一页是否顺手。") {
                    TextField("反馈原因", text: $feedbackReason, axis: .vertical)
                        .lineLimit(1...3)
                        .textFieldStyle(.roundedBorder)
                        .disabled(isSubmittingFeedback)

                    Button {
                        Task {
                            await submitLatestTurnFeedback(session: session, turn: turn)
                        }
                    } label: {
                        if isSubmittingFeedback {
                            HStack(spacing: 8) {
                                ProgressView()
                                Text("提交中")
                            }
                        } else {
                            Label("提交反馈", systemImage: "hand.thumbsup")
                        }
                    }
                    .buttonStyle(.bordered)
                    .disabled(!canSubmitFeedback)

                    feedbackStatusContent
                }
            }
        }
    }

    @ViewBuilder
    private func cachedStoryOpenContent(session: DeviceSessionState) -> some View {
        switch cachedStoryOpenState {
        case .idle:
            EmptyView()

        case .opening:
            StoryHomePanel(title: "恢复故事", subtitle: nil) {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("正在读取故事...")
                        .font(.subheadline)
                        .foregroundStyle(Color(red: 0.34, green: 0.29, blue: 0.22))
                }
            }

        case .failed(let message):
            StoryHomePanel(title: "恢复故事", subtitle: nil) {
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .font(.subheadline)
                    .foregroundStyle(.red)
            }

        case .opened(let story):
            VStack(alignment: .leading, spacing: 16) {
                let resumedChoices = ResumedStoryChoiceParser.choices(from: story.latestTurns)

                StoryHomePanel(title: "已打开故事", subtitle: story.title) {
                    ForEach(storyStateSummaryLines(for: story.currentState), id: \.self) { line in
                        Label(line, systemImage: "bookmark.fill")
                            .font(.caption)
                            .foregroundStyle(Color(red: 0.34, green: 0.29, blue: 0.22))
                    }
                }

                if story.latestTurns.isEmpty {
                    StoryHomePanel(title: "最近页", subtitle: nil) {
                        Text("暂无最近回合。")
                            .font(.subheadline)
                            .foregroundStyle(Color(red: 0.34, green: 0.29, blue: 0.22))
                    }
                } else {
                    ForEach(Array(story.latestTurns.enumerated()), id: \.offset) { index, turn in
                        StoryBookPageView(
                            pageLabel: "最近页 \(index + 1)",
                            title: nil,
                            narrative: stringValue(from: turn, key: "narrative") ?? "已读取最近回合。",
                            progressText: nil,
                            progressValue: nil,
                            stateLines: [],
                            isTurning: false
                        )
                    }
                }

                StoryHomePanel(title: "继续翻页", subtitle: "从缓存故事继续阅读。") {
                    if canSelectResumedChoice && !resumedChoices.isEmpty {
                        ForEach(resumedChoices) { choice in
                            ChoiceButtonRow(choice: choice) {
                                Task {
                                    await playResumedSuggestedChoice(
                                        session: session,
                                        story: story,
                                        choice: choice
                                    )
                                }
                            }
                            .disabled(isPlayingTurn)
                        }
                    }

                    TextField("继续行动", text: $freeTextTurnInput, axis: .vertical)
                        .lineLimit(2...4)
                        .textFieldStyle(.roundedBorder)
                        .disabled(isPlayingTurn)

                    Button {
                        Task {
                            await playFreeTextTurn(session: session, storyID: story.storyID)
                        }
                    } label: {
                        Label("提交行动", systemImage: "paperplane.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!canSubmitFreeTextTurn)

                    turnStatusContent(loadingText: "正在继续故事...")
                }
            }
        }
    }

    private var isCreatingStory: Bool {
        if case .creating = storyCreationState {
            return true
        }

        return false
    }

    private var hasActiveStoryPage: Bool {
        if latestPlayedTurn != nil {
            return true
        }

        if case .created = storyCreationState {
            return true
        }

        return false
    }

    private var hasOpenedCachedStory: Bool {
        switch cachedStoryOpenState {
        case .idle:
            return false
        case .opening, .opened, .failed:
            return true
        }
    }

    private var storyCreationFailureMessage: String? {
        if case .failed(let message) = storyCreationState {
            return message
        }

        return nil
    }

    private var isPlayingTurn: Bool {
        if case .playing = storyTurnState {
            return true
        }

        return false
    }

    private var isSubmittingFeedback: Bool {
        if case .submitting = feedbackSubmissionState {
            return true
        }

        return false
    }

    private var canSelectResumedChoice: Bool {
        switch storyTurnState {
        case .idle, .failed:
            return true
        case .playing, .played:
            return false
        }
    }

    private var isOpeningCachedStory: Bool {
        loadingCachedStoryID != nil
    }

    private var loadingCachedStoryID: String? {
        if case .opening(let storyID) = cachedStoryOpenState {
            return storyID
        }

        return nil
    }

    private var trimmedFreeTextTurnInput: String {
        freeTextTurnInput.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var canSubmitFreeTextTurn: Bool {
        !isPlayingTurn && !trimmedFreeTextTurnInput.isEmpty
    }

    private var trimmedFeedbackReason: String {
        feedbackReason.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var canSubmitFeedback: Bool {
        !isSubmittingFeedback && !trimmedFeedbackReason.isEmpty
    }

    @ViewBuilder
    private func turnStatusContent(loadingText: String) -> some View {
        if case .playing = storyTurnState {
            HStack(spacing: 8) {
                ProgressView()
                Text(loadingText)
                    .font(.subheadline)
                    .foregroundStyle(Color(red: 0.34, green: 0.29, blue: 0.22))
            }
        }

        if case .failed(let message) = storyTurnState {
            Label(message, systemImage: "exclamationmark.triangle.fill")
                .font(.subheadline)
                .foregroundStyle(.red)
        }
    }

    @ViewBuilder
    private var feedbackStatusContent: some View {
        switch feedbackSubmissionState {
        case .idle:
            EmptyView()
        case .submitting:
            Text("正在提交反馈...")
                .font(.subheadline)
                .foregroundStyle(Color(red: 0.34, green: 0.29, blue: 0.22))
        case .submitted:
            Text("反馈已提交。")
                .font(.subheadline)
                .foregroundStyle(.green)
        case .failed(let message):
            Text(message)
                .font(.subheadline)
                .foregroundStyle(.red)
        }
    }

    private func openingStateSummaryLines(for state: [String: JSONValue]) -> [String] {
        var lines: [String] = []

        if let activeGoal = stringValue(from: state, key: "active_goal") {
            lines.append("目标：\(activeGoal)")
        }

        if let shortSummary = stringValue(from: state, key: "short_summary") {
            lines.append("摘要：\(shortSummary)")
        }

        return lines
    }

    private func latestTurnPageLabel(for turn: PlayTurnResponse) -> String {
        "第 \(turn.chapterProgress.currentChapterIndex) 章 · 第 \(turn.chapterProgress.currentSceneIndex) 页"
    }

    private func latestTurnProgressText(for turn: PlayTurnResponse) -> String {
        "场景进度 \(turn.chapterProgress.progressPercent)%"
    }

    private func latestTurnProgressValue(for turn: PlayTurnResponse) -> Double {
        min(Double(turn.chapterProgress.progressPercent) / 100, 1)
    }

    private var activeStoryCache: any StoryCaching {
        storyCache ?? SwiftDataStoryCache(modelContext: modelContext)
    }

    private func openCachedStory(_ story: LocalStory) async {
        guard let storyID = UUID(uuidString: story.storyID) else {
            cachedStoryOpenState = .failed("无法打开缓存故事：本地故事 ID 无效。")
            return
        }

        selectedTemplateID = nil
        storyCreationState = .idle
        storyTurnState = .idle
        latestPlayedTurn = nil
        freeTextTurnInput = ""
        resetFeedbackDraft()
        cachedStoryOpenState = .opening(story.storyID)

        do {
            let fetchedStory = try await storyReader.fetchStory(storyID: storyID)
            cachedStoryOpenState = .opened(fetchedStory)
        } catch {
            cachedStoryOpenState = .failed(error.localizedDescription)
        }
    }

    private func playResumedSuggestedChoice(
        session: DeviceSessionState,
        story: GetStoryResponse,
        choice: StoryChoice
    ) async {
        await playChoiceTurn(session: session, storyID: story.storyID, choice: choice)
    }

    private func createStory(session: DeviceSessionState, template: StoryTemplate) async {
        didValidateProtagonist = true

        guard let request = protagonistDraft.makeCreateStoryRequest(
            deviceID: session.deviceID,
            templateID: template.id
        ) else {
            storyCreationState = .idle
            storyTurnState = .idle
            latestPlayedTurn = nil
            return
        }

        storyCreationState = .creating
        storyTurnState = .idle
        latestPlayedTurn = nil
        cachedStoryOpenState = .idle
        freeTextTurnInput = ""
        resetFeedbackDraft()

        do {
            let story = try await storyClient.createStory(request)
            storyCreationState = .created(story)
            storyTurnState = .idle
            latestPlayedTurn = nil
            freeTextTurnInput = ""
            cacheCreatedStory(story, template: template)
        } catch {
            storyCreationState = .failed(error.localizedDescription)
            storyTurnState = .idle
            latestPlayedTurn = nil
            freeTextTurnInput = ""
        }
    }

    private func playSuggestedChoice(
        session: DeviceSessionState,
        story: CreateStoryResponse,
        choice: StoryChoice
    ) async {
        await playChoiceTurn(session: session, storyID: story.storyID, choice: choice)
    }

    private func playLatestTurnSuggestedChoice(
        session: DeviceSessionState,
        turn: PlayTurnResponse,
        choice: StoryChoice
    ) async {
        await playChoiceTurn(session: session, storyID: turn.storyID, choice: choice)
    }

    private func playChoiceTurn(
        session: DeviceSessionState,
        storyID: UUID,
        choice: StoryChoice
    ) async {
        withAnimation(.easeInOut(duration: 0.20)) {
            storyTurnState = .playing
        }
        resetFeedbackDraft()

        do {
            let request = PlayTurnRequest.choice(deviceID: session.deviceID, choiceID: choice.id)
            let turn = try await turnClient.playTurn(storyID: storyID, request: request)
            freeTextTurnInput = ""
            withAnimation(.easeInOut(duration: 0.36)) {
                latestPlayedTurn = turn
                storyTurnState = .played(turn)
            }
            cachePlayedTurn(turn)
        } catch {
            withAnimation(.easeInOut(duration: 0.20)) {
                storyTurnState = .failed(error.localizedDescription)
            }
        }
    }

    private func playFreeTextTurn(
        session: DeviceSessionState,
        storyID: UUID
    ) async {
        let userText = trimmedFreeTextTurnInput
        guard !userText.isEmpty else {
            return
        }

        withAnimation(.easeInOut(duration: 0.20)) {
            storyTurnState = .playing
        }
        resetFeedbackDraft()

        do {
            let request = PlayTurnRequest.freeText(deviceID: session.deviceID, userText: userText)
            let turn = try await turnClient.playTurn(storyID: storyID, request: request)
            freeTextTurnInput = ""
            withAnimation(.easeInOut(duration: 0.36)) {
                latestPlayedTurn = turn
                storyTurnState = .played(turn)
            }
            cachePlayedTurn(turn)
        } catch {
            withAnimation(.easeInOut(duration: 0.20)) {
                storyTurnState = .failed(error.localizedDescription)
            }
        }
    }

    private func submitLatestTurnFeedback(
        session: DeviceSessionState,
        turn: PlayTurnResponse
    ) async {
        let reason = trimmedFeedbackReason
        guard !reason.isEmpty else {
            return
        }

        feedbackSubmissionState = .submitting

        do {
            let request = FeedbackRequest(
                deviceID: session.deviceID,
                storyID: turn.storyID,
                turnID: turn.turnID,
                rating: .neutral,
                reason: reason,
                freeText: nil
            )
            _ = try await feedbackClient.submitFeedback(request)
            feedbackReason = ""
            feedbackSubmissionState = .submitted
        } catch {
            feedbackSubmissionState = .failed(error.localizedDescription)
        }
    }

    private func resetFeedbackDraft() {
        feedbackSubmissionState = .idle
        feedbackReason = ""
    }

    private func cacheCreatedStory(_ story: CreateStoryResponse, template: StoryTemplate) {
        try? activeStoryCache.upsertCreatedStory(
            story,
            templateID: template.id,
            locale: AppConfig.defaultLocale
        )
    }

    private func cachePlayedTurn(_ turn: PlayTurnResponse) {
        try? activeStoryCache.upsertPlayedTurn(turn)
    }

    private func storyStateSummaryLines(for state: [String: JSONValue]) -> [String] {
        var lines: [String] = []

        let templateID = stringValue(from: state, key: "template_id")
        let chapter = intValue(from: state, key: "current_chapter_index")
        let scene = intValue(from: state, key: "current_scene_index")
        let turnCount = intValue(from: state, key: "turn_count")

        var progressParts: [String] = []
        if let templateID {
            progressParts.append(templateID)
        }
        if let chapter {
            progressParts.append("第 \(chapter) 章")
        }
        if let scene {
            progressParts.append("场景 \(scene)")
        }
        if let turnCount {
            progressParts.append("\(turnCount) 回合")
        }
        if !progressParts.isEmpty {
            lines.append(progressParts.joined(separator: " · "))
        }

        if let activeGoal = stringValue(from: state, key: "active_goal") {
            lines.append("目标：\(activeGoal)")
        }

        if let shortSummary = stringValue(from: state, key: "short_summary") {
            lines.append("摘要：\(shortSummary)")
        }

        if let updatedAt = stringValue(from: state, key: "updated_at") {
            lines.append("更新：\(updatedAt)")
        }

        return lines.isEmpty ? ["已读取当前故事状态。"] : lines
    }

    private func intValue(from object: [String: JSONValue], key: String) -> Int? {
        guard let value = object[key] else {
            return nil
        }

        if case .int(let intValue) = value {
            return intValue
        }

        return nil
    }

    private func stringValue(from object: [String: JSONValue], key: String) -> String? {
        guard let value = object[key] else {
            return nil
        }

        if case .string(let stringValue) = value {
            let trimmedValue = stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmedValue.isEmpty ? nil : trimmedValue
        }

        return nil
    }
}

#Preview {
    ContentView(
        viewModel: LaunchHomeViewModel(
            initialState: .loaded(
                session: DeviceSessionState(
                    deviceID: UUID(uuidString: "11111111-1111-4111-8111-111111111111")!,
                    userID: UUID(uuidString: "22222222-2222-4222-8222-222222222222")!,
                    dailyTurnLimit: 50,
                    turnsUsedToday: 0
                ),
                templates: [
                    StoryTemplate(
                        id: "xianxia_rise",
                        name: "修仙逆袭",
                        genre: "修仙",
                        shortDescription: "从边缘小人物开始，踏入宗门、秘境和天命之争。",
                        tags: ["升级", "宗门", "秘境", "爽文"],
                        recommendedTone: ["热血", "暗线", "成长"]
                    )
                ]
            )
        )
    )
    .modelContainer(for: [
        LocalStory.self,
        LocalTurn.self
    ], inMemory: true)
}
