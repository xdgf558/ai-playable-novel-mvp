import Foundation

final class APIClient {
    private enum HTTPMethod: String {
        case get = "GET"
        case post = "POST"
    }

    private let baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(
        baseURL: URL = AppConfig.backendBaseURL,
        session: URLSession = .shared,
        decoder: JSONDecoder = JSONDecoder(),
        encoder: JSONEncoder = JSONEncoder()
    ) {
        self.baseURL = baseURL
        self.session = session
        self.decoder = decoder
        self.encoder = encoder
    }

    func createDeviceSession(_ request: DeviceSessionRequest) async throws -> DeviceSessionResponse {
        try await post(path: "v1/device-session", body: request)
    }

    func fetchTemplates(locale: String = AppConfig.defaultLocale) async throws -> TemplatesResponse {
        try await get(path: "v1/templates", queryItems: [
            URLQueryItem(name: "locale", value: locale)
        ])
    }

    func createStory(_ request: CreateStoryRequest) async throws -> CreateStoryResponse {
        try await post(path: "v1/stories", body: request)
    }

    func fetchStory(storyID: UUID) async throws -> GetStoryResponse {
        try await get(path: "v1/stories/\(storyID.uuidString)")
    }

    func listStories(deviceID: UUID) async throws -> ListStoriesResponse {
        try await get(path: "v1/stories", queryItems: [
            URLQueryItem(name: "device_id", value: deviceID.uuidString)
        ])
    }

    func playTurn(storyID: UUID, request: PlayTurnRequest) async throws -> PlayTurnResponse {
        try await post(path: "v1/stories/\(storyID.uuidString)/turns", body: request)
    }

    func submitFeedback(_ request: FeedbackRequest) async throws -> FeedbackResponse {
        try await post(path: "v1/feedback", body: request)
    }

    private func get<Response: Decodable>(
        path: String,
        queryItems: [URLQueryItem] = []
    ) async throws -> Response {
        try await send(path: path, method: .get, queryItems: queryItems, bodyData: nil)
    }

    private func post<Response: Decodable, Body: Encodable>(
        path: String,
        body: Body
    ) async throws -> Response {
        let bodyData: Data

        do {
            bodyData = try encoder.encode(body)
        } catch {
            throw APIClientError.encoding(error)
        }

        return try await send(path: path, method: .post, bodyData: bodyData)
    }

    private func send<Response: Decodable>(
        path: String,
        method: HTTPMethod,
        queryItems: [URLQueryItem] = [],
        bodyData: Data?
    ) async throws -> Response {
        let url = try makeURL(path: path, queryItems: queryItems)
        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        if let bodyData {
            request.httpBody = bodyData
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        let data: Data
        let response: URLResponse

        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIClientError.transport(error)
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIClientError.invalidResponse
        }

        guard (200..<300).contains(httpResponse.statusCode) else {
            if let errorEnvelope = try? decoder.decode(APIErrorEnvelope.self, from: data) {
                throw APIClientError.api(errorEnvelope.error, statusCode: httpResponse.statusCode)
            }

            throw APIClientError.httpStatus(httpResponse.statusCode)
        }

        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw APIClientError.decoding(error)
        }
    }

    private func makeURL(path: String, queryItems: [URLQueryItem]) throws -> URL {
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            throw APIClientError.invalidURL(path)
        }

        let basePath = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let routePath = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let fullPath = [basePath, routePath].filter { !$0.isEmpty }.joined(separator: "/")
        components.path = "/" + fullPath
        components.queryItems = queryItems.isEmpty ? nil : queryItems

        guard let url = components.url else {
            throw APIClientError.invalidURL(path)
        }

        return url
    }
}

enum APIClientError: Error, LocalizedError {
    case invalidURL(String)
    case invalidResponse
    case encoding(Error)
    case transport(Error)
    case decoding(Error)
    case api(APIErrorDetail, statusCode: Int)
    case httpStatus(Int)

    var errorDescription: String? {
        switch self {
        case .invalidURL(let path):
            "Invalid API URL for path: \(path)"
        case .invalidResponse:
            "Backend returned an invalid response."
        case .encoding(let error):
            "Could not encode API request: \(error.localizedDescription)"
        case .transport(let error):
            "Could not reach backend: \(error.localizedDescription)"
        case .decoding(let error):
            "Could not decode backend response: \(error.localizedDescription)"
        case .api(let detail, _):
            detail.message
        case .httpStatus(let statusCode):
            "Backend returned HTTP \(statusCode)."
        }
    }
}
