import SwiftUI

struct RestaurantDetailView: View {
    let restaurant: Restaurant
    let criteria: SearchCriteria
    @State private var navigateToBooking = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                AsyncImage(url: restaurant.photoURL) { image in
                    image.resizable().aspectRatio(contentMode: .fill)
                } placeholder: {
                    Color.gray.opacity(0.15)
                        .overlay(Image(systemName: "photo").font(.largeTitle).foregroundStyle(.gray))
                }
                .frame(maxWidth: .infinity, minHeight: 240, maxHeight: 240)
                .clipped()

                VStack(alignment: .leading, spacing: 16) {
                    // Header
                    VStack(alignment: .leading, spacing: 6) {
                        Text(restaurant.name)
                            .font(.title2.bold())

                        HStack(spacing: 12) {
                            Label(String(format: "%.1f", restaurant.rating), systemImage: "star.fill")
                                .foregroundStyle(.orange)
                            Text("\(restaurant.userRatingCount) reviews")
                                .foregroundStyle(.secondary)
                            if let price = restaurant.priceLevel?.displayString, !price.isEmpty {
                                Text(price).foregroundStyle(.secondary)
                            }
                        }
                        .font(.subheadline)

                        Text(restaurant.address)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }

                    Divider()

                    // Availability / booking
                    if restaurant.hasAvailability {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Available Shifts")
                                .font(.headline)
                            ForEach(restaurant.availableSlots) { slot in
                                Label(slot.shiftName, systemImage: "clock")
                                    .font(.subheadline)
                                    .foregroundStyle(.green)
                            }
                        }

                        Button { navigateToBooking = true } label: {
                            Text("Book Now")
                                .fontWeight(.semibold)
                                .frame(maxWidth: .infinity)
                                .padding()
                                .background(Color.accentColor)
                                .foregroundStyle(.white)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .padding(.top, 4)

                    } else if let websiteString = restaurant.websiteURI, let url = URL(string: websiteString) {
                        Text("Online booking is not available for your selected date and party size.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)

                        Link(destination: url) {
                            Label("Visit Website", systemImage: "globe")
                                .fontWeight(.semibold)
                                .frame(maxWidth: .infinity)
                                .padding()
                                .background(Color.secondary.opacity(0.12))
                                .foregroundStyle(.primary)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                    } else {
                        Text("No booking information available.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding()
            }
        }
        .navigationTitle(restaurant.name)
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(isPresented: $navigateToBooking) {
            BookingContainerView(viewModel: BookingViewModel(restaurant: restaurant, criteria: criteria))
        }
    }
}
