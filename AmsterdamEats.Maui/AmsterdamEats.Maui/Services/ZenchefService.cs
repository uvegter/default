using System.Net.Http.Json;
using System.Text.RegularExpressions;
using AmsterdamEats.Config;
using AmsterdamEats.Models;

namespace AmsterdamEats.Services;

public class ZenchefService
{
    private readonly HttpClient _http;

    public ZenchefService(HttpClient http) => _http = http;

    // Fetches the restaurant's own website and scans for a Zenchef booking widget embed code.
    public async Task<int?> ResolveRestaurantIdAsync(Restaurant restaurant)
    {
        if (string.IsNullOrEmpty(restaurant.WebsiteUri)) return null;
        try
        {
            var html = await _http.GetStringAsync(restaurant.WebsiteUri);
            return ExtractZenchefId(html);
        }
        catch { return null; }
    }

    private static int? ExtractZenchefId(string html)
    {
        string[] patterns =
        [
            @"data-restaurant-id=""(\d+)""",
            @"[?&]rid=(\d+)",
            @"restaurant_id[""'\s]*[:=][""'\s]*(\d+)",
            @"zenchef\.com[^""']*[?&]rid=(\d+)"
        ];
        foreach (var pattern in patterns)
        {
            var match = Regex.Match(html, pattern);
            if (match.Success && int.TryParse(match.Groups[1].Value, out var id))
                return id;
        }
        return null;
    }

    public async Task<List<ZenchefSlot>> CheckAvailabilityAsync(int restaurantId, SearchCriteria criteria)
    {
        var dateString = criteria.Date.ToString("yyyy-MM-dd");
        var url = $"{ApiConfig.ZenchefMiddlewareBaseUrl}/getAvailabilitiesSummary" +
                  $"?restaurantId={restaurantId}&date_begin={dateString}&date_end={dateString}";
        try
        {
            var shifts = await _http.GetFromJsonAsync<List<ZenchefShift>>(url) ?? [];
            return shifts
                .Where(s => !s.Closed
                    && s.PossibleGuests.Contains(criteria.NumberOfPeople)
                    && s.Schedule.Date == dateString)
                .Select(s => new ZenchefSlot { Id = s.Id, ShiftName = s.Name, Date = s.Schedule.Date })
                .ToList();
        }
        catch { return []; }
    }
}
