using AmsterdamEats.ViewModels;

namespace AmsterdamEats.Views;

public partial class SearchPage : ContentPage
{
    private readonly SearchViewModel _viewModel;

    public SearchPage(SearchViewModel viewModel)
    {
        InitializeComponent();
        _viewModel = viewModel;
        BindingContext = viewModel;
        DatePickerControl.MinimumDate = DateTime.Today;
    }

    private async void OnSearchClicked(object sender, EventArgs e)
    {
        var criteria = _viewModel.BuildCriteria();
        await Shell.Current.GoToAsync(nameof(ResultsPage), new Dictionary<string, object>
        {
            { "Criteria", criteria }
        });
    }
}
