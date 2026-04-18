using AmsterdamEats.Config;

namespace AmsterdamEats.Models;

public class BookingRequest
{
    public int ZenchefRestaurantId { get; set; }
    public string Date { get; set; } = string.Empty;
    public int Pax { get; set; }
    public string RestaurantName { get; set; } = string.Empty;

    public string WidgetUrl =>
        $"{ApiConfig.ZenchefBookingBaseUrl}/results?rid={ZenchefRestaurantId}&pax={Pax}&day={Date}";
}
