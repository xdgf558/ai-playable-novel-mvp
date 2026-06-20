import Foundation

enum AppConfig {
    static let backendBaseURL = URL(string: "http://127.0.0.1:8000")!
    static let defaultLocale = "zh-Hans"
    static let appVersion = "0.1.0"
}

enum AppBrand {
    static let productName = "StoryCat"
    static let chineseName = "故事猫"
    static let stationCatByline = "by Station Cat"
    static let appStoreEnglishTitle = "StoryCat: AI Playable Novel"
    static let appStoreChineseTitle = "StoryCat 故事猫"
    static let taglineEnglish = "Create a hero, enter a living novel, and shape the story chapter by chapter."
    static let taglineChinese = "创建你的主角，进入一部会回应你的长篇故事。"
    static let loadingMessage = "正在翻开故事"
    static let connectionMessage = "连接 StoryCat 服务器中..."
}
