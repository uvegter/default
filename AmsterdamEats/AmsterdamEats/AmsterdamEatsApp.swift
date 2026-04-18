import SwiftUI

@main
struct AmsterdamEatsApp: App {
    var body: some Scene {
        WindowGroup {
            NavigationStack {
                SearchView()
            }
        }
    }
}
