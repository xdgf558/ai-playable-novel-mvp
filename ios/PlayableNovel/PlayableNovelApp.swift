import SwiftData
import SwiftUI

@main
struct PlayableNovelApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .modelContainer(for: [
            LocalStory.self,
            LocalTurn.self
        ])
    }
}
