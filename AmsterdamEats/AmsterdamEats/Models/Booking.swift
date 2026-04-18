import Foundation

struct BookingRequest {
    let zenchefRestaurantId: Int
    let date: String
    let pax: Int
    let restaurantName: String

    var widgetURL: URL {
        URL(string: "\(APIConfig.zenchefBookingBaseURL)/results?rid=\(zenchefRestaurantId)&pax=\(pax)&day=\(date)")!
    }
}
