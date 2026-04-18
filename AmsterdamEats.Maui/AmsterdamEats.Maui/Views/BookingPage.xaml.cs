using AmsterdamEats.Models;
using AmsterdamEats.ViewModels;

namespace AmsterdamEats.Views;

[QueryProperty(nameof(Restaurant), "Restaurant")]
[QueryProperty(nameof(Criteria), "Criteria")]
public partial class BookingPage : ContentPage
{
    private readonly BookingViewModel _viewModel;

    public Restaurant? Restaurant { get; set; }
    public SearchCriteria? Criteria { get; set; }

    public BookingPage(BookingViewModel viewModel)
    {
        InitializeComponent();
        _viewModel = viewModel;
        BindingContext = viewModel;
    }

    protected override void OnNavigatedTo(NavigatedToEventArgs args)
    {
        base.OnNavigatedTo(args);
        if (Restaurant is null || Criteria is null) return;

        _viewModel.Prepare(Restaurant, Criteria);
        if (_viewModel.BookingRequest?.WidgetUrl is { } url)
            BookingWebView.Source = new UrlWebViewSource { Url = url };
    }

    private async void OnOpenInBrowserClicked(object sender, EventArgs e)
    {
        var url = _viewModel.BookingRequest?.WidgetUrl;
        if (url is not null && Uri.TryCreate(url, UriKind.Absolute, out var uri))
            await Launcher.OpenAsync(uri);
    }
}
