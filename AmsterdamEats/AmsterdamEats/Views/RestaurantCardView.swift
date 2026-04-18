import SwiftUI

struct RestaurantCardView: View {
    let restaurant: Restaurant

    var body: some View {
        HStack(spacing: 12) {
            AsyncImage(url: restaurant.photoURL) { image in
                image.resizable().aspectRatio(contentMode: .fill)
            } placeholder: {
                Color.gray.opacity(0.15)
                    .overlay(Image(systemName: "fork.knife").foregroundStyle(.gray))
            }
            .frame(width: 72, height: 72)
            .clipShape(RoundedRectangle(cornerRadius: 10))

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(restaurant.name)
                        .font(.headline)
                        .lineLimit(1)
                    Spacer()
                    availabilityBadge
                }

                Text(restaurant.address)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                HStack(spacing: 8) {
                    Label(String(format: "%.1f", restaurant.rating), systemImage: "star.fill")
                        .foregroundStyle(.orange)
                    Text("(\(restaurant.userRatingCount))")
                        .foregroundStyle(.secondary)
                    if let price = restaurant.priceLevel?.displayString, !price.isEmpty {
                        Text(price).foregroundStyle(.secondary)
                    }
                }
                .font(.caption)
            }
        }
        .padding(.vertical, 4)
        .opacity(restaurant.availabilityChecked && !restaurant.hasAvailability ? 0.55 : 1)
    }

    @ViewBuilder
    private var availabilityBadge: some View {
        if restaurant.hasAvailability {
            Text("Available")
                .font(.caption2)
                .fontWeight(.semibold)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.green.opacity(0.15))
                .foregroundStyle(.green)
                .clipShape(Capsule())
        } else if restaurant.availabilityChecked && !restaurant.isBookable {
            Text("No booking")
                .font(.caption2)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.secondary.opacity(0.1))
                .foregroundStyle(.secondary)
                .clipShape(Capsule())
        }
    }
}
