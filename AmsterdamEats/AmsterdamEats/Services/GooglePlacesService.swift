import Foundation

final class GooglePlacesService {
    private let client = NetworkClient.shared

    // MARK: - Response types

    private struct PlacesResponse: Decodable {
        let places: [PlaceResult]?
    }

    private struct PlaceResult: Decodable {
        let id: String
        let displayName: DisplayName
        let formattedAddress: String?
        let rating: Double?
        let userRatingCount: Int?
        let priceLevel: Restaurant.PriceLevelDisplay?
        let websiteUri: String?
        let photos: [Photo]?

        struct DisplayName: Decodable { let text: String }
        struct Photo: Decodable { let name: String }
    }

    // MARK: - Public API

    func searchRestaurants(criteria: SearchCriteria) async throws -> [Restaurant] {
        guard let url = URL(string: "\(APIConfig.googlePlacesBaseURL)/places:searchText") else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(APIConfig.googlePlacesAPIKey, forHTTPHeaderField: "X-Goog-Api-Key")
        request.setValue(
            "places.id,places.displayName,places.formattedAddress,places.rating," +
            "places.userRatingCount,places.priceLevel,places.websiteUri,places.photos",
            forHTTPHeaderField: "X-Goog-FieldMask"
        )

        let selectedPriceLevels = criteria.priceRange.isEmpty
            ? SearchCriteria.PriceLevel.allCases.map(\.rawValue)
            : criteria.priceRange.map(\.rawValue)

        let body: [String: Any] = [
            "textQuery": "\(criteria.cuisineType.queryPrefix) Amsterdam",
            "includedType": "restaurant",
            "locationRestriction": [
                "circle": [
                    "center": ["latitude": APIConfig.amsterdamLatitude, "longitude": APIConfig.amsterdamLongitude],
                    "radius": APIConfig.searchRadiusMeters
                ]
            ],
            "priceLevels": selectedPriceLevels,
            "minRating": 3.5,
            "rankPreference": "RELEVANCE",
            "pageSize": 20
        ]

        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let response: PlacesResponse = try await client.fetch(request: request)
        return (response.places ?? [])
            .map { place in
                Restaurant(
                    id: place.id,
                    name: place.displayName.text,
                    address: place.formattedAddress ?? "",
                    rating: place.rating ?? 0,
                    userRatingCount: place.userRatingCount ?? 0,
                    priceLevel: place.priceLevel,
                    websiteURI: place.websiteUri,
                    photoName: place.photos?.first?.name
                )
            }
            .sorted { $0.rating > $1.rating }
    }
}
