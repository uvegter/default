namespace AmsterdamEats.Models;

public class SearchCriteria
{
    public DateTime Date { get; set; } = DateTime.Today.AddDays(1);
    public TimeSpan Time { get; set; } = new TimeSpan(19, 0, 0);
    public int NumberOfPeople { get; set; } = 2;
    public CuisineType Cuisine { get; set; } = CuisineType.Any;
    public HashSet<PriceLevel> PriceRange { get; set; } = [PriceLevel.Moderate];
    public string DateString => Date.ToString("yyyy-MM-dd");
}

public enum CuisineType
{
    Any, Italian, Japanese, French, Dutch, Indian, Thai, American, Mediterranean, Chinese, Mexican
}

public enum PriceLevel
{
    Budget, Moderate, Expensive, VeryExpensive
}
