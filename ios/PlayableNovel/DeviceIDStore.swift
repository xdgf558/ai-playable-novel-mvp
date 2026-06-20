import Foundation
import Security

final class DeviceIDStore: DeviceIDStoring {
    private let service: String
    private let account: String

    init(
        service: String = Bundle.main.bundleIdentifier ?? "com.xdgf558.playablenovel",
        account: String = "anonymous-device-id"
    ) {
        self.service = service
        self.account = account
    }

    func loadOrCreateDeviceID() throws -> UUID {
        if let existingDeviceID = try loadDeviceID() {
            return existingDeviceID
        }

        let newDeviceID = UUID()
        try saveDeviceID(newDeviceID)
        return newDeviceID
    }

    private func loadDeviceID() throws -> UUID? {
        var query = keychainLookupQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)

        if status == errSecItemNotFound {
            return nil
        }

        guard status == errSecSuccess else {
            throw DeviceIDStoreError.keychainFailure(operation: "load", status: status)
        }

        guard
            let data = item as? Data,
            let storedValue = String(data: data, encoding: .utf8),
            let deviceID = UUID(uuidString: storedValue)
        else {
            throw DeviceIDStoreError.invalidStoredValue
        }

        return deviceID
    }

    private func saveDeviceID(_ deviceID: UUID) throws {
        let valueData = Data(deviceID.uuidString.utf8)
        let updateAttributes: [String: Any] = [
            kSecValueData as String: valueData,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]
        let updateStatus = SecItemUpdate(keychainLookupQuery() as CFDictionary, updateAttributes as CFDictionary)

        if updateStatus == errSecSuccess {
            return
        }

        guard updateStatus == errSecItemNotFound else {
            throw DeviceIDStoreError.keychainFailure(operation: "update", status: updateStatus)
        }

        var addQuery = keychainLookupQuery()
        addQuery[kSecValueData as String] = valueData
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly

        let addStatus = SecItemAdd(addQuery as CFDictionary, nil)

        guard addStatus == errSecSuccess else {
            throw DeviceIDStoreError.keychainFailure(operation: "save", status: addStatus)
        }
    }

    private func keychainLookupQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
    }
}

enum DeviceIDStoreError: Error, LocalizedError {
    case invalidStoredValue
    case keychainFailure(operation: String, status: OSStatus)

    var errorDescription: String? {
        switch self {
        case .invalidStoredValue:
            return "Stored device ID is not a valid UUID."
        case .keychainFailure(let operation, let status):
            let statusMessage = SecCopyErrorMessageString(status, nil) as String? ?? "OSStatus \(status)"
            return "Could not \(operation) device ID from Keychain: \(statusMessage)."
        }
    }
}
