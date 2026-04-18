using AmsterdamEats.Models;
using AmsterdamEats.ViewModels;

namespace AmsterdamEats.Views;

[QueryProperty(nameof(Criteria), "Criteria")]
public partial class ResultsPage : ContentPage
{
    private readonly ResultsViewModel _viewModel;
    private SearchCriteria? _criteria;

    public SearchCriteria? Criteria
    {
        set
        {
            _criteria = value;
            if (value is not null)
                _ = _viewModel.LoadAsync(value);
        }
    }

    public ResultsPage(ResultsViewModel viewModel)
    {
        InitializeComponent();
        _viewModel = viewModel;
        BindingContext = viewModel;
    }

    private async void OnRestaurantSelected(object sender, SelectionChangedEventArgs e)
    {
        if (e.CurrentSelection.FirstOrDefault() is not Restaurant restaurant || _criteria is null) return;

        // Clear selection so tapping the same item again still navigates
        if (sender is CollectionView cv) cv.SelectedItem = null;

        await Shell.Current.GoToAsync(nameof(RestaurantDetailPage), new Dictionary<string, object>
        {
            { "Restaurant", restaurant },
            { "Criteria",   _criteria  }
        });
    }
}
