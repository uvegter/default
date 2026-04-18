using AmsterdamEats.Services;
using AmsterdamEats.ViewModels;
using AmsterdamEats.Views;

namespace AmsterdamEats;

public static class MauiProgram
{
    public static MauiApp CreateMauiApp()
    {
        var builder = MauiApp.CreateBuilder();
        builder.UseMauiApp<App>();

        // Shared HttpClient for all services
        builder.Services.AddSingleton<HttpClient>();

        // Services (singleton — stateless)
        builder.Services.AddSingleton<GooglePlacesService>();
        builder.Services.AddSingleton<ZenchefService>();

        // ViewModels
        builder.Services.AddSingleton<SearchViewModel>();
        builder.Services.AddTransient<ResultsViewModel>();
        builder.Services.AddTransient<RestaurantDetailViewModel>();
        builder.Services.AddTransient<BookingViewModel>();

        // Pages
        builder.Services.AddSingleton<AppShell>();
        builder.Services.AddSingleton<SearchPage>();
        builder.Services.AddTransient<ResultsPage>();
        builder.Services.AddTransient<RestaurantDetailPage>();
        builder.Services.AddTransient<BookingPage>();

        return builder.Build();
    }
}
