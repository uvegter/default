import Foundation

struct SearchCriteria {
    var date: Date = Date()
    var time: Date = Calendar.current.date(bySettingHour: 19, minute: 0, second: 0, of: Date()) ?? Date()
    var numberOfPeople: Int = 2
    var cuisineType: CuisineType = .any
    var priceRange: Set<PriceLevel> = [.moderate]

    enum CuisineType: String, CaseIterable, Identifiable {
        case any, italian, japanese, french, dutch, indian, thai, american, mediterranean, chinese, mexican
        var id: String { rawValue }
        var displayName: String { rawValue.capitalized }
        var queryPrefix: String { self == .any ? "restaurant" : "\(rawValue) restaurant" }
    }

    enum PriceLevel: String, CaseIterable, Identifiable, Hashable {
        case budget = "PRICE_LEVEL_INEXPENSIVE"
        case moderate = "PRICE_LEVEL_MODERATE"
        case expensive = "PRICE_LEVEL_EXPENSIVE"
        case veryExpensive = "PRICE_LEVEL_VERY_EXPENSIVE"
        var id: String { rawValue }
        var displayName: String {
            switch self {
            case .budget: return "€  (Budget)"
            case .moderate: return "€€  (Moderate)"
            case .expensive: return "€€€  (Expensive)"
            case .veryExpensive: return "€€€€  (Fine Dining)"
            }
        }
    }
}
