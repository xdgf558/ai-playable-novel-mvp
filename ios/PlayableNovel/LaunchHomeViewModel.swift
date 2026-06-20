import Combine
import Foundation

protocol TemplateCatalogFetching {
    func fetchTemplates(locale: String) async throws -> TemplatesResponse
}

extension APIClient: TemplateCatalogFetching {}

enum LaunchHomeState: Equatable {
    case idle
    case loading
    case loaded(session: DeviceSessionState, templates: [StoryTemplate])
    case failed(LaunchHomeErrorState)
}

struct LaunchHomeErrorState: Equatable {
    let message: String
}

@MainActor
final class LaunchHomeViewModel: ObservableObject {
    @Published private(set) var state: LaunchHomeState

    private let sessionBootstrapper: DeviceSessionBootstrapping
    private let templateClient: TemplateCatalogFetching
    private let locale: String

    init(
        sessionBootstrapper: DeviceSessionBootstrapping = DeviceSessionBootstrapper(),
        templateClient: TemplateCatalogFetching = APIClient(),
        locale: String = AppConfig.defaultLocale,
        initialState: LaunchHomeState = .idle
    ) {
        self.sessionBootstrapper = sessionBootstrapper
        self.templateClient = templateClient
        self.locale = locale
        self.state = initialState
    }

    func load() async {
        state = .loading

        do {
            let session = try await sessionBootstrapper.bootstrap()
            let templatesResponse = try await templateClient.fetchTemplates(locale: locale)
            state = .loaded(session: session, templates: templatesResponse.templates)
        } catch {
            state = .failed(LaunchHomeErrorState(message: error.localizedDescription))
        }
    }

    func retry() async {
        await load()
    }
}
