import Foundation

struct Restaurant: Identifiable {
    let id: String
    let name: String
    let address: String
    let rating: Double
    let userRatingCount: Int
    let priceLevel: PriceLevelDisplay?
    let websiteURI: String?
    let photoName: String?
    var zenchefRestaurantId: Int?
    var availableSlots: [ZenchefSlot] = []
    var availabilityChecked: Bool = false

    enum PriceLevelDisplay: String, Decodable {
        case unspecified = "PRICE_LEVEL_UNSPECIFIED"
        case free = "PRICE_LEVEL_FREE"
        case inexpensive = "PRICE_LEVEL_INEXPENSIVE"
        case moderate = "PRICE_LEVEL_MODERATE"
        case expensive = "PRICE_LEVEL_EXPENSIVE"
        case veryExpensive = "PRICE_LEVEL_VERY_EXPENSIVE"

        var displayString: String {
            switch self {
            case .unspecified, .free: return ""
            case .inexpensive: return "€"
            case .moderate: return "€€"
            case .expensive: return "€€€"
            case .veryExpensive: return "€€€€"
            }
        }
    }

    var photoURL: URL? {
        guard let photoName else { return nil }
        return URL(string: "\(APIConfig.googlePlacesBaseURL)/\(photoName)/media?maxHeightPx=400&maxWidthPx=400&key=\(APIConfig.googlePlacesAPIKey)")
    }

    var hasAvailability: Bool { !availableSlots.isEmpty }
    var isBookable: Bool { zenchefRestaurantId != nil }
}
