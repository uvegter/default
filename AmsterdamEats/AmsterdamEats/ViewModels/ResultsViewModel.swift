import Foundation

@MainActor
final class ResultsViewModel: ObservableObject {
    enum ViewState {
        case idle
        case loading
        case loaded([Restaurant])
        case error(String)
    }

    @Published var state: ViewState = .idle

    private let placesService = GooglePlacesService()
    private let zenchefService = ZenchefService()

    func load(criteria: SearchCriteria) async {
        state = .loading
        do {
            var restaurants = try await placesService.searchRestaurants(criteria: criteria)
            state = .loaded(restaurants)

            // Check Zenchef availability for all restaurants in parallel
            await withTaskGroup(of: (Int, Int?, [ZenchefSlot]).self) { group in
                for (index, restaurant) in restaurants.enumerated() {
                    group.addTask {
                        let rid = await self.zenchefService.resolveRestaurantId(for: restaurant)
                        var slots: [ZenchefSlot] = []
                        if let rid {
                            slots = (try? await self.zenchefService.checkAvailability(
                                restaurantId: rid, criteria: criteria)) ?? []
                        }
                        return (index, rid, slots)
                    }
                }
                for await (index, rid, slots) in group {
                    restaurants[index].zenchefRestaurantId = rid
                    restaurants[index].availableSlots = slots
                    restaurants[index].availabilityChecked = true
                }
            }

            // Available + bookable first, then by Google rating
            restaurants.sort {
                if $0.hasAvailability != $1.hasAvailability { return $0.hasAvailability }
                return $0.rating > $1.rating
            }
            state = .loaded(restaurants)
        } catch {
            state = .error(error.localizedDescription)
        }
    }
}
