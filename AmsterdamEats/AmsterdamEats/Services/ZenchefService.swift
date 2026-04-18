import Foundation

final class ZenchefService {
    private let client = NetworkClient.shared

    // Attempts to extract a Zenchef restaurant ID by fetching the restaurant's website
    // and scanning the HTML for the Zenchef booking widget embed code.
    func resolveRestaurantId(for restaurant: Restaurant) async -> Int? {
        guard let websiteString = restaurant.websiteURI,
              let websiteURL = URL(string: websiteString) else { return nil }
        guard let html = try? await client.fetchRaw(url: websiteURL) else { return nil }
        return extractZenchefId(from: html)
    }

    private func extractZenchefId(from html: String) -> Int? {
        let patterns = [
            #"data-restaurant-id="(\d+)""#,
            #"[?&]rid=(\d+)"#,
            #"restaurant_id["'\s]*[:=]["'\s]*(\d+)"#,
            #"zenchef\.com[^"']*[?&]rid=(\d+)"#
        ]
        for pattern in patterns {
            guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
            let range = NSRange(html.startIndex..., in: html)
            if let match = regex.firstMatch(in: html, range: range),
               let captureRange = Range(match.range(at: 1), in: html),
               let id = Int(html[captureRange]) {
                return id
            }
        }
        return nil
    }

    func checkAvailability(restaurantId: Int, criteria: SearchCriteria) async throws -> [ZenchefSlot] {
        let dateString = DateFormatter.zenchefDate.string(from: criteria.date)
        let urlString = "\(APIConfig.zenchefMiddlewareBaseURL)/getAvailabilitiesSummary" +
            "?restaurantId=\(restaurantId)&date_begin=\(dateString)&date_end=\(dateString)"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let shifts: [ZenchefShift] = try await client.fetch(request: request)
        return shifts
            .filter { !$0.closed && $0.possibleGuests.contains(criteria.numberOfPeople) && $0.schedule.date == dateString }
            .map { ZenchefSlot(id: $0.id, shiftName: $0.name, date: $0.schedule.date) }
    }
}
