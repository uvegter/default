import Foundation

@MainActor
final class SearchViewModel: ObservableObject {
    @Published var criteria = SearchCriteria()

    var isValid: Bool {
        criteria.numberOfPeople >= 1 && !criteria.priceRange.isEmpty
    }
}
