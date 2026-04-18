using AmsterdamEats.Config;

namespace AmsterdamEats.Models;

public class Restaurant
{
    public string Id { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public string Address { get; set; } = string.Empty;
    public double Rating { get; set; }
    public int UserRatingCount { get; set; }
    public string? PriceLevelDisplay { get; set; }
    public string? WebsiteUri { get; set; }
    public string? PhotoName { get; set; }
    public int? ZenchefRestaurantId { get; set; }
    public List<ZenchefSlot> AvailableSlots { get; set; } = [];
    public bool AvailabilityChecked { get; set; }

    public bool HasAvailability => AvailableSlots.Count > 0;
    public bool IsBookable => ZenchefRestaurantId.HasValue;
    public bool HasWebsite => !string.IsNullOrEmpty(WebsiteUri);

    public string RatingDisplay => $"★ {Rating:F1}";
    public string ReviewCountDisplay => $"({UserRatingCount:N0} reviews)";
    public string AvailabilityBadge => HasAvailability ? "Available"
        : (AvailabilityChecked && !IsBookable ? "No booking" : string.Empty);
    public bool ShowAvailabilityBadge => !string.IsNullOrEmpty(AvailabilityBadge);

    public string PhotoUrl => PhotoName is not null
        ? $"{ApiConfig.GooglePlacesBaseUrl}/{PhotoName}/media?maxHeightPx=400&maxWidthPx=400&key={ApiConfig.GooglePlacesApiKey}"
        : string.Empty;
}
