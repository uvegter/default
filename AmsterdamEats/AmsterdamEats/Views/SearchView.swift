import SwiftUI

struct SearchView: View {
    @StateObject private var viewModel = SearchViewModel()
    @State private var navigateToResults = false

    var body: some View {
        Form {
            Section("When") {
                DatePicker("Date", selection: $viewModel.criteria.date, in: Date()..., displayedComponents: .date)
                DatePicker("Time", selection: $viewModel.criteria.time, displayedComponents: .hourAndMinute)
            }

            Section("Party Size") {
                Stepper("People: \(viewModel.criteria.numberOfPeople)", value: $viewModel.criteria.numberOfPeople, in: 1...20)
            }

            Section("Cuisine") {
                Picker("Type", selection: $viewModel.criteria.cuisineType) {
                    ForEach(SearchCriteria.CuisineType.allCases) { type in
                        Text(type.displayName).tag(type)
                    }
                }
            }

            Section("Price Range") {
                ForEach(SearchCriteria.PriceLevel.allCases) { level in
                    Toggle(level.displayName, isOn: Binding(
                        get: { viewModel.criteria.priceRange.contains(level) },
                        set: { isOn in
                            if isOn { viewModel.criteria.priceRange.insert(level) }
                            else { viewModel.criteria.priceRange.remove(level) }
                        }
                    ))
                }
            }

            Section {
                Button {
                    navigateToResults = true
                } label: {
                    HStack {
                        Spacer()
                        Text("Find Restaurants")
                            .fontWeight(.semibold)
                        Spacer()
                    }
                }
                .disabled(!viewModel.isValid)
            }
        }
        .navigationTitle("Amsterdam Eats")
        .navigationDestination(isPresented: $navigateToResults) {
            ResultsView(criteria: viewModel.criteria)
        }
    }
}
