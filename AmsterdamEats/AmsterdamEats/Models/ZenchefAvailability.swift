import Foundation

struct ZenchefShift: Decodable {
    let id: Int
    let name: String
    let closed: Bool
    let possibleGuests: [Int]
    let schedule: Schedule

    struct Schedule: Decodable {
        let date: String
    }

    private enum CodingKeys: String, CodingKey {
        case id, name, closed, schedule
        case possibleGuests = "possible_guests"
    }
}

struct ZenchefSlot: Identifiable {
    let id: Int
    let shiftName: String
    let date: String
}
