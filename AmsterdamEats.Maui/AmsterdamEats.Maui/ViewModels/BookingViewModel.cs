using CommunityToolkit.Mvvm.ComponentModel;
using AmsterdamEats.Models;

namespace AmsterdamEats.ViewModels;

public partial class BookingViewModel : ObservableObject
{
    [ObservableProperty]
    private BookingRequest? _bookingRequest;

    public void Prepare(Restaurant restaurant, SearchCriteria criteria)
    {
        BookingRequest = new BookingRequest
        {
            ZenchefRestaurantId = restaurant.ZenchefRestaurantId ?? 0,
            Date = criteria.DateString,
            Pax = criteria.NumberOfPeople,
            RestaurantName = restaurant.Name
        };
    }
}
