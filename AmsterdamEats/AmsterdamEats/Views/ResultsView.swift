import SwiftUI

struct ResultsView: View {
    let criteria: SearchCriteria
    @StateObject private var viewModel = ResultsViewModel()

    var body: some View {
        Group {
            switch viewModel.state {
            case .idle:
                Color.clear
            case .loading:
                VStack(spacing: 16) {
                    ProgressView()
                    Text("Finding available restaurants…")
                        .foregroundStyle(.secondary)
                }
            case .loaded(let restaurants):
                if restaurants.isEmpty {
                    ContentUnavailableView(
                        "No Restaurants Found",
                        systemImage: "fork.knife",
                        description: Text("Try adjusting your search criteria.")
                    )
                } else {
                    List(restaurants) { restaurant in
                        NavigationLink(destination: RestaurantDetailView(restaurant: restaurant, criteria: criteria)) {
                            RestaurantCardView(restaurant: restaurant)
                        }
                    }
                    .listStyle(.plain)
                }
            case .error(let message):
                ContentUnavailableView(
                    "Something Went Wrong",
                    systemImage: "exclamationmark.triangle",
                    description: Text(message)
                )
            }
        }
        .navigationTitle("Results")
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.load(criteria: criteria) }
    }
}
