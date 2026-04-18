using AmsterdamEats.Views;

namespace AmsterdamEats;

public partial class AppShell : Shell
{
    public AppShell()
    {
        InitializeComponent();
        Routing.RegisterRoute(nameof(ResultsPage),          typeof(ResultsPage));
        Routing.RegisterRoute(nameof(RestaurantDetailPage), typeof(RestaurantDetailPage));
        Routing.RegisterRoute(nameof(BookingPage),          typeof(BookingPage));
    }
}
