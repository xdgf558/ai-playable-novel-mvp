import Foundation

protocol DeviceIDStoring {
    func loadOrCreateDeviceID() throws -> UUID
}

protocol DeviceSessionCreating {
    func createDeviceSession(_ request: DeviceSessionRequest) async throws -> DeviceSessionResponse
}

extension APIClient: DeviceSessionCreating {}

protocol DeviceSessionBootstrapping {
    func bootstrap() async throws -> DeviceSessionState
}

struct DeviceSessionState: Equatable {
    let deviceID: UUID
    let userID: UUID
    let dailyTurnLimit: Int
    let turnsUsedToday: Int
}

final class DeviceSessionBootstrapper {
    private let deviceIDStore: DeviceIDStoring
    private let apiClient: DeviceSessionCreating
    private let locale: String
    private let appVersion: String

    init(
        deviceIDStore: DeviceIDStoring = DeviceIDStore(),
        apiClient: DeviceSessionCreating = APIClient(),
        locale: String = AppConfig.defaultLocale,
        appVersion: String = AppConfig.appVersion
    ) {
        self.deviceIDStore = deviceIDStore
        self.apiClient = apiClient
        self.locale = locale
        self.appVersion = appVersion
    }

    func bootstrap() async throws -> DeviceSessionState {
        let deviceID = try deviceIDStore.loadOrCreateDeviceID()
        let response = try await apiClient.createDeviceSession(
            DeviceSessionRequest(
                deviceID: deviceID,
                appVersion: appVersion,
                locale: locale
            )
        )

        return DeviceSessionState(
            deviceID: response.deviceID,
            userID: response.userID,
            dailyTurnLimit: response.dailyTurnLimit,
            turnsUsedToday: response.turnsUsedToday
        )
    }
}

extension DeviceSessionBootstrapper: DeviceSessionBootstrapping {}
