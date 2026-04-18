import SwiftUI
import WebKit

// WKWebView wrapper that loads the Zenchef booking widget
struct BookingWebView: UIViewRepresentable {
    let url: URL
    weak var navigationDelegate: WKNavigationDelegate?

    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView()
        webView.navigationDelegate = navigationDelegate
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        webView.load(URLRequest(url: url))
    }
}

struct BookingContainerView: View {
    @ObservedObject var viewModel: BookingViewModel
    @State private var coordinator = NavigationCoordinator()

    var body: some View {
        ZStack {
            BookingWebView(url: viewModel.bookingRequest.widgetURL, navigationDelegate: coordinator)
                .ignoresSafeArea(edges: .bottom)
                .onReceive(coordinator.$didFail) { failed in
                    if failed { viewModel.loadFailed = true }
                }

            if viewModel.loadFailed {
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.largeTitle)
                        .foregroundStyle(.orange)
                    Text("Could not load the booking page.")
                        .multilineTextAlignment(.center)
                    Link("Open in Safari", destination: viewModel.bookingRequest.widgetURL)
                        .buttonStyle(.borderedProminent)
                }
                .padding(32)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16))
                .padding()
            }
        }
        .navigationTitle("Book \(viewModel.bookingRequest.restaurantName)")
        .navigationBarTitleDisplayMode(.inline)
    }
}

// WKNavigationDelegate that publishes navigation failures via Combine
@MainActor
final class NavigationCoordinator: NSObject, ObservableObject, WKNavigationDelegate {
    @Published var didFail = false

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        didFail = true
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        didFail = true
    }
}
