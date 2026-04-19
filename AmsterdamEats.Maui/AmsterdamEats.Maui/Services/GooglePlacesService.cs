using System.Net.Http.Json;
using System.Text.Json.Serialization;
using AmsterdamEats.Config;
using AmsterdamEats.Models;

namespace AmsterdamEats.Services;

public class GooglePlacesService
{
    private readonly HttpClient _http;

    public GooglePlacesService(HttpClient http) => _http = http;

    public async Task<List<Restaurant>> SearchRestaurantsAsync(SearchCriteria criteria)
    {
        var request = new HttpRequestMessage(HttpMethod.Post, $"{ApiConfig.GooglePlacesBaseUrl}/places:searchText");
        request.Headers.Add("X-Goog-Api-Key", ApiConfig.GooglePlacesApiKey);
        request.Headers.Add("X-Goog-FieldMask",
            "places.id,places.displayName,places.formattedAddress,places.rating," +
            "places.userRatingCount,places.priceLevel,places.websiteUri,places.photos");

        var priceLevels = criteria.PriceRange.Count == 0
            ? Enum.GetValues<PriceLevel>().Select(MapPriceLevel).ToList()
            : criteria.PriceRange.Select(MapPriceLevel).ToList();

        var body = new
        {
            textQuery = $"{GetQueryPrefix(criteria.Cuisine)} Amsterdam",
            includedType = "restaurant",
            locationRestriction = new
            {
                circle = new
                {
                    center = new { latitude = ApiConfig.AmsterdamLatitude, longitude = ApiConfig.AmsterdamLongitude },
                    radius = ApiConfig.SearchRadiusMeters
                }
            },
            priceLevels,
            minRating = 3.5,
            rankPreference = "RELEVANCE",
            maxResultCount = 20
        };

        request.Content = JsonContent.Create(body);
        var response = await _http.SendAsync(request);
        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync();
            throw new HttpRequestException($"Google Places API error {(int)response.StatusCode}: {errorBody}");
        }

        var result = await response.Content.ReadFromJsonAsync<PlacesResponse>();
        return (result?.Places ?? [])
            .Select(p => new Restaurant
            {
                Id = p.Id ?? string.Empty,
                Name = p.DisplayName?.Text ?? string.Empty,
                Address = p.FormattedAddress ?? string.Empty,
                Rating = p.Rating ?? 0,
                UserRatingCount = p.UserRatingCount ?? 0,
                PriceLevelDisplay = MapPriceLevelToSymbol(p.PriceLevel),
                WebsiteUri = p.WebsiteUri,
                PhotoName = p.Photos?.FirstOrDefault()?.Name
            })
            .OrderByDescending(r => r.Rating)
            .ToList();
    }

    private static string GetQueryPrefix(CuisineType cuisine) =>
        cuisine == CuisineType.Any ? "restaurant" : $"{cuisine.ToString().ToLower()} restaurant";

    private static string MapPriceLevel(PriceLevel level) => level switch
    {
        PriceLevel.Budget => "PRICE_LEVEL_INEXPENSIVE",
        PriceLevel.Moderate => "PRICE_LEVEL_MODERATE",
        PriceLevel.Expensive => "PRICE_LEVEL_EXPENSIVE",
        PriceLevel.VeryExpensive => "PRICE_LEVEL_VERY_EXPENSIVE",
        _ => "PRICE_LEVEL_MODERATE"
    };

    private static string? MapPriceLevelToSymbol(string? level) => level switch
    {
        "PRICE_LEVEL_INEXPENSIVE" => "€",
        "PRICE_LEVEL_MODERATE" => "€€",
        "PRICE_LEVEL_EXPENSIVE" => "€€€",
        "PRICE_LEVEL_VERY_EXPENSIVE" => "€€€€",
        _ => null
    };

    // Private response DTOs
    private class PlacesResponse
    {
        [JsonPropertyName("places")] public List<PlaceResult>? Places { get; set; }
    }

    private class PlaceResult
    {
        [JsonPropertyName("id")] public string? Id { get; set; }
        [JsonPropertyName("displayName")] public PlaceDisplayName? DisplayName { get; set; }
        [JsonPropertyName("formattedAddress")] public string? FormattedAddress { get; set; }
        [JsonPropertyName("rating")] public double? Rating { get; set; }
        [JsonPropertyName("userRatingCount")] public int? UserRatingCount { get; set; }
        [JsonPropertyName("priceLevel")] public string? PriceLevel { get; set; }
        [JsonPropertyName("websiteUri")] public string? WebsiteUri { get; set; }
        [JsonPropertyName("photos")] public List<PlacePhoto>? Photos { get; set; }
    }

    private class PlaceDisplayName
    {
        [JsonPropertyName("text")] public string Text { get; set; } = string.Empty;
    }

    private class PlacePhoto
    {
        [JsonPropertyName("name")] public string Name { get; set; } = string.Empty;
    }
}
