using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using AmsterdamEats.Config;
using AmsterdamEats.Models;

namespace AmsterdamEats.Services;

public class ZenchefService
{
    private readonly HttpClient _http;

    public ZenchefService(HttpClient http) => _http = http;

    public async Task<int?> ResolveRestaurantIdAsync(Restaurant restaurant)
    {
        if (string.IsNullOrEmpty(restaurant.WebsiteUri)) return null;
        try
        {
            var req = new HttpRequestMessage(HttpMethod.Get, restaurant.WebsiteUri);
            req.Headers.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36");
            var response = await _http.SendAsync(req);
            if (!response.IsSuccessStatusCode) return null;
            var html = await response.Content.ReadAsStringAsync();
            return ExtractZenchefId(html);
        }
        catch { return null; }
    }

    private static int? ExtractZenchefId(string html)
    {
        string[] patterns =
        [
            @"data-restaurant-id=""(\d+)""",
            @"data-rid=""(\d+)""",
            @"data-zenchef-id=""(\d+)""",
            @"[?&]rid=(\d+)",
            @"bookings\.zenchef\.com/results\?rid=(\d+)",
            @"restaurant_id[""'\s]*[:=][""'\s]*(\d+)",
            @"""restaurant_id""\s*:\s*(\d+)",
            @"restaurantId[""'\s]*[:=][""'\s]*(\d+)",
            @"zenchef\.com[^""']*[?&]rid=(\d+)"
        ];
        foreach (var pattern in patterns)
        {
            var match = Regex.Match(html, pattern, RegexOptions.IgnoreCase);
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
            using var response = await _http.GetAsync(url);
            if (!response.IsSuccessStatusCode) return [];

            var json = await response.Content.ReadAsStringAsync();

            // Try direct array first
            List<ZenchefShift>? shifts = null;
            try { shifts = JsonSerializer.Deserialize<List<ZenchefShift>>(json); }
            catch { }

            // Try wrapped object {"shifts":[...]} or {"data":[...]}
            if (shifts == null || shifts.Count == 0)
            {
                try
                {
                    var wrapped = JsonSerializer.Deserialize<ZenchefShiftsWrapper>(json);
                    shifts = wrapped?.Shifts ?? wrapped?.Data;
                }
                catch { }
            }

            return (shifts ?? [])
                .Where(s => !s.Closed && s.PossibleGuests.Contains(criteria.NumberOfPeople))
                .Select(s => new ZenchefSlot { Id = s.Id, ShiftName = s.Name, Date = s.Schedule.Date })
                .ToList();
        }
        catch { return []; }
    }

    private class ZenchefShiftsWrapper
    {
        [JsonPropertyName("shifts")] public List<ZenchefShift>? Shifts { get; set; }
        [JsonPropertyName("data")] public List<ZenchefShift>? Data { get; set; }
    }
}
