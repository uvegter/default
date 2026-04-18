import Foundation

extension DateFormatter {
    static let zenchefDate: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()
}
