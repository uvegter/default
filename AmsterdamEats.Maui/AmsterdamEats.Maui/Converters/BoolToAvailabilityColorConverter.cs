using System.Globalization;

namespace AmsterdamEats.Converters;

public class BoolToAvailabilityColorConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        value is true ? Colors.Green : Color.FromArgb("#888888");

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotImplementedException();
}
