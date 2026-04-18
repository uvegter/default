import Foundation

enum APIError: LocalizedError {
    case badStatus(Int)
    case invalidURL
    case noData

    var errorDescription: String? {
        switch self {
        case .badStatus(let code): return "Server returned status \(code)"
        case .invalidURL: return "Invalid URL"
        case .noData: return "No data received"
        }
    }
}

final class NetworkClient {
    static let shared = NetworkClient()
    private init() {}

    func fetch<T: Decodable>(request: URLRequest) async throws -> T {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.badStatus((response as? HTTPURLResponse)?.statusCode ?? -1)
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    func fetchRaw(url: URL) async throws -> String {
        let (data, response) = try await URLSession.shared.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.badStatus((response as? HTTPURLResponse)?.statusCode ?? -1)
        }
        return String(data: data, encoding: .utf8) ?? ""
    }
}
