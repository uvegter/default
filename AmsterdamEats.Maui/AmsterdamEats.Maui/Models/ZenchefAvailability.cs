using System.Text.Json.Serialization;

namespace AmsterdamEats.Models;

public class ZenchefShift
{
    [JsonPropertyName("id")] public int Id { get; set; }
    [JsonPropertyName("name")] public string Name { get; set; } = string.Empty;
    [JsonPropertyName("closed")] public bool Closed { get; set; }
    [JsonPropertyName("possible_guests")] public List<int> PossibleGuests { get; set; } = [];
    [JsonPropertyName("schedule")] public ZenchefSchedule Schedule { get; set; } = new();
}

public class ZenchefSchedule
{
    [JsonPropertyName("date")] public string Date { get; set; } = string.Empty;
}

public class ZenchefSlot
{
    public int Id { get; set; }
    public string ShiftName { get; set; } = string.Empty;
    public string Date { get; set; } = string.Empty;
}
