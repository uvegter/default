using CommunityToolkit.Mvvm.ComponentModel;
using AmsterdamEats.Models;

namespace AmsterdamEats.ViewModels;

public partial class RestaurantDetailViewModel : ObservableObject
{
    [ObservableProperty]
    private Restaurant? _restaurant;

    public SearchCriteria? Criteria { get; set; }
}
