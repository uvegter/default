using CommunityToolkit.Mvvm.ComponentModel;
using AmsterdamEats.Models;

namespace AmsterdamEats.ViewModels;

public partial class SearchViewModel : ObservableObject
{
    [ObservableProperty]
    private DateTime _date = DateTime.Today.AddDays(1);

    [ObservableProperty]
    private TimeSpan _time = new(19, 0, 0);

    [ObservableProperty]
    private int _numberOfPeople = 2;

    [ObservableProperty]
    private int _selectedCuisineIndex = 0;

    public List<string> CuisineTypeNames { get; } =
        Enum.GetValues<CuisineType>().Select(c => c.ToString()).ToList();

    public List<PriceLevelOption> PriceLevelOptions { get; } =
    [
        new() { Level = PriceLevel.Budget,       DisplayName = "€    Budget",      IsSelected = false },
        new() { Level = PriceLevel.Moderate,     DisplayName = "€€   Moderate",    IsSelected = true  },
        new() { Level = PriceLevel.Expensive,    DisplayName = "€€€  Expensive",   IsSelected = false },
        new() { Level = PriceLevel.VeryExpensive,DisplayName = "€€€€ Fine Dining", IsSelected = false }
    ];

    public SearchCriteria BuildCriteria() => new()
    {
        Date = Date,
        Time = Time,
        NumberOfPeople = NumberOfPeople,
        Cuisine = (CuisineType)SelectedCuisineIndex,
        PriceRange = PriceLevelOptions.Where(p => p.IsSelected).Select(p => p.Level).ToHashSet()
    };
}
