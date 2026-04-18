using CommunityToolkit.Mvvm.ComponentModel;

namespace AmsterdamEats.Models;

public partial class PriceLevelOption : ObservableObject
{
    public PriceLevel Level { get; init; }
    public string DisplayName { get; init; } = string.Empty;

    [ObservableProperty]
    private bool _isSelected;
}
