using AmsterdamEats.Models;
using AmsterdamEats.ViewModels;

namespace AmsterdamEats.Views;

[QueryProperty(nameof(Restaurant), "Restaurant")]
[QueryProperty(nameof(Criteria), "Criteria")]
public partial class RestaurantDetailPage : ContentPage
{
    private readonly RestaurantDetailViewModel _viewModel;

    public Restaurant? Restaurant
    {
        set
        {
            if (value is not null)
                _viewModel.Restaurant = value;
        }
    }

    public SearchCriteria? Criteria
    {
        set => _viewModel.Criteria = value;
    }

    public RestaurantDetailPage(RestaurantDetailViewModel viewModel)
    {
        InitializeComponent();
        _viewModel = viewModel;
        BindingContext = viewModel;
    }

    private async void OnBookNowClicked(object sender, EventArgs e)
    {
        if (_viewModel.Restaurant is null || _viewModel.Criteria is null) return;
        await Shell.Current.GoToAsync(nameof(BookingPage), new Dictionary<string, object>
        {
            { "Restaurant", _viewModel.Restaurant },
            { "Criteria",   _viewModel.Criteria   }
        });
    }

    private async void OnVisitWebsiteClicked(object sender, EventArgs e)
    {
        var uri = _viewModel.Restaurant?.WebsiteUri;
        if (uri is not null && Uri.TryCreate(uri, UriKind.Absolute, out var url))
            await Launcher.OpenAsync(url);
    }
}
