using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using AmsterdamEats.Models;
using AmsterdamEats.Services;

namespace AmsterdamEats.ViewModels;

public partial class ResultsViewModel : ObservableObject
{
    private readonly GooglePlacesService _placesService;
    private readonly ZenchefService _zenchefService;

    public ResultsViewModel(GooglePlacesService placesService, ZenchefService zenchefService)
    {
        _placesService = placesService;
        _zenchefService = zenchefService;
    }

    [ObservableProperty]
    private ObservableCollection<Restaurant> _restaurants = [];

    [ObservableProperty]
    private bool _isLoading;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasError))]
    private string? _errorMessage;

    public bool HasError => !string.IsNullOrEmpty(ErrorMessage);

    public async Task LoadAsync(SearchCriteria criteria)
    {
        IsLoading = true;
        ErrorMessage = null;
        Restaurants = [];

        try
        {
            var results = await _placesService.SearchRestaurantsAsync(criteria);
            Restaurants = new ObservableCollection<Restaurant>(results);

            // Check all restaurants' Zenchef availability in parallel
            var tasks = results.Select(async r =>
            {
                var rid = await _zenchefService.ResolveRestaurantIdAsync(r);
                var slots = rid.HasValue
                    ? await _zenchefService.CheckAvailabilityAsync(rid.Value, criteria)
                    : [];
                return (Restaurant: r, Rid: rid, Slots: slots);
            });

            foreach (var (restaurant, rid, slots) in await Task.WhenAll(tasks))
            {
                restaurant.ZenchefRestaurantId = rid;
                restaurant.AvailableSlots = slots;
                restaurant.AvailabilityChecked = true;
            }

            // Available + bookable first, then by Google rating
            Restaurants = new ObservableCollection<Restaurant>(
                results.OrderByDescending(r => r.HasAvailability).ThenByDescending(r => r.Rating));
        }
        catch (Exception ex)
        {
            ErrorMessage = ex.Message;
        }
        finally
        {
            IsLoading = false;
        }
    }
}
