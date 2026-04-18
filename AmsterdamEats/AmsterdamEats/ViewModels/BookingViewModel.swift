import Foundation

@MainActor
final class BookingViewModel: ObservableObject {
    @Published var loadFailed = false
    let bookingRequest: BookingRequest

    init(restaurant: Restaurant, criteria: SearchCriteria) {
        let dateString = DateFormatter.zenchefDate.string(from: criteria.date)
        bookingRequest = BookingRequest(
            zenchefRestaurantId: restaurant.zenchefRestaurantId ?? 0,
            date: dateString,
            pax: criteria.numberOfPeople,
            restaurantName: restaurant.name
        )
    }
}
