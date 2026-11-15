import SwiftUI

struct ContentView: View {
    @StateObject private var service = KrogerService()
    @State private var query = ""
    @State private var products: [KrogerProduct] = []
    @State private var errorMessage: String?
    @State private var confirmationMessage: String?
    @State private var isSettingsPresented = false
    @State private var isReceiptsPresented = false
    @State private var isBuyAgainPresented = false
    
    var body: some View {
        NavigationStack {
            Group {
                if products.isEmpty {
                    VStack(spacing: 16) {
                        Button("Search") {
                            Task { await recommend() }
                        }
                        .buttonStyle(.borderedProminent)
                        .accessibilityIdentifier("searchButton")

                        ContentUnavailableView(
                            "Find groceries",
                            systemImage: "cart",
                            description: Text("Search for a product to see Kroger recommendations.")
                        )
                    }
                } else {
                    List(products) { product in
                        ProductRow(product: product) { quantity in
                            Task { await add(product, quantity: quantity) }
                        }
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Kroger")
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always), prompt: "Search products")
            .accessibilityIdentifier("productSearchField")
            .accessibilityLabel("Product search")
            .onSubmit(of: .search) {
                Task { await recommend() }
            }
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button {
                        isReceiptsPresented = true
                    } label: {
                        Image(systemName: "receipt")
                    }
                    .accessibilityIdentifier("receiptsButton")
                    .accessibilityLabel("Receipts")

                    Button {
                        isBuyAgainPresented = true
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .accessibilityIdentifier("buyAgainButton")
                    .accessibilityLabel("Buy Again")

                    Button {
                        isSettingsPresented = true
                    } label: {
                        Image(systemName: "gear")
                    }
                    .accessibilityIdentifier("settingsButton")
                    .accessibilityLabel("Kroger settings")
                }
            }
            .overlay {
                if service.isLoading {
                    ProgressView("Finding recommendations…")
                }
            }
            .alert("Kroger", isPresented: Binding(
                get: { errorMessage != nil },
                set: { if !$0 { errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(errorMessage ?? "")
            }
            .alert("Added to cart", isPresented: Binding(
                get: { confirmationMessage != nil },
                set: { if !$0 { confirmationMessage = nil } }
            )) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(confirmationMessage ?? "")
            }
            .sheet(isPresented: $isSettingsPresented) {
                SettingsView(service: service)
            }
            .sheet(isPresented: $isReceiptsPresented) {
                ReceiptsView(index: service.receiptIndex)
            }
            .sheet(isPresented: $isBuyAgainPresented) {
                BuyAgainView(index: service.receiptIndex)
            }
        }
    }
    
    private func recommend() async {
        do {
            errorMessage = nil
            products = try await service.recommend(query: query)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
    
    private func add(_ product: KrogerProduct, quantity: Int) async {
        do {
            try await service.add(upc: product.upc, quantity: quantity)
            confirmationMessage = "\(quantity) × \(product.description) was added to your Kroger cart."
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct ProductRow: View {
    let product: KrogerProduct
    let addAction: (Int) -> Void
    @State private var quantity = 1
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(product.description)
                        .font(.headline)
                    if let brand = product.brand, !brand.isEmpty {
                        Text(brand)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(product.displayPrice)
                        .font(.headline)
                    HStack(spacing: 4) {
                        Text(product.displaySize)
                        Text(product.displayUnitPrice)
                            .accessibilityIdentifier("unitPriceLabel")
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
            }
            
            if product.previouslyPurchased, let date = product.latestPurchaseDate {
                HStack {
                    Spacer()
                    Label("Previously purchased · \(date)", systemImage: "checkmark.circle")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if product.unwantedIngredientCount.map({ $0 > 0 }) ?? true {
                HStack {
                    Spacer()
                    Text(product.preferenceSummary)
                        .accessibilityIdentifier("preferenceSummaryLabel")
                        .foregroundStyle(.secondary)
                }
                .font(.caption)

                HStack {
                    Spacer()
                    Label("Unwanted: \(product.displayUnwantedCount)", systemImage: "exclamationmark.triangle")
                        .accessibilityIdentifier("unwantedCountLabel")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            
            HStack {
                Text("UPC \(product.upc)")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                Spacer()
                HStack(spacing: 0) {
                    Button {
                        quantity = max(1, quantity - 1)
                    } label: {
                        Image(systemName: "minus")
                            .frame(width: 36, height: 32)
                    }
                    .disabled(quantity == 1)
                    .accessibilityIdentifier("decrementQuantity_\(product.upc)")
                    .accessibilityLabel("Decrease quantity")

                    Divider()
                        .frame(height: 20)

                    Text("\(quantity)")
                        .frame(width: 28, height: 32)
                        .accessibilityIdentifier("quantityValue_\(product.upc)")
                        .accessibilityLabel("Quantity \(quantity)")

                    Divider()
                        .frame(height: 20)

                    Button {
                        quantity = min(99, quantity + 1)
                    } label: {
                        Image(systemName: "plus")
                            .frame(width: 36, height: 32)
                    }
                    .accessibilityIdentifier("incrementQuantity_\(product.upc)")
                    .accessibilityLabel("Increase quantity")
                }
                .buttonStyle(.borderless)
                .background(Capsule().fill(.gray.opacity(0.18)))
                .accessibilityIdentifier("quantityStepper_\(product.upc)")
                .accessibilityLabel("Quantity for \(product.description): \(quantity)")
                Button("Add to cart") {
                    addAction(quantity)
                }
                    .buttonStyle(.borderedProminent)
                    .accessibilityIdentifier("addToCartButton_\(product.upc)")
                    .accessibilityLabel("Add \(quantity) \(product.description) to cart")
            }
        }
        .padding(.vertical, 6)
    }
}

private struct SettingsView: View {
    @ObservedObject var service: KrogerService
    @Environment(\.dismiss) private var dismiss
    @State private var showClientID = false
    @State private var showClientSecret = false
    @State private var authError: String?
    
    var body: some View {
        NavigationStack {
            Form {
                Section("Kroger account") {
                    Label(
                        service.isAuthenticated ? "Signed in to Kroger" : "Not signed in",
                        systemImage: service.isAuthenticated ? "checkmark.circle.fill" : "person.crop.circle"
                    )
                    .foregroundStyle(service.isAuthenticated ? .green : .secondary)
                    Button(service.isAuthenticated ? "Sign out" : "Sign in to Kroger") {
                        Task {
                            do {
                                if service.isAuthenticated {
                                    service.logout()
                                } else {
                                    try await service.login()
                                }
                            } catch {
                                authError = error.localizedDescription
                            }
                        }
                    }
                    .accessibilityIdentifier(service.isAuthenticated ? "signOutButton" : "signInButton")
                }
                Section("Kroger API") {
                    HStack {
                        Group {
                            if showClientID {
                                TextField("Client ID", text: Binding(
                                    get: { service.clientID },
                                    set: { service.clientID = $0 }
                                ))
                            } else {
                                SecureField("Client ID", text: Binding(
                                    get: { service.clientID },
                                    set: { service.clientID = $0 }
                                ))
                            }
                        }
                        Button {
                            showClientID.toggle()
                        } label: {
                            Image(systemName: showClientID ? "eye.slash" : "eye")
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("toggleClientIDVisibility")
                        .accessibilityLabel(showClientID ? "Hide client ID" : "Show client ID")
                    }
                    HStack {
                        Group {
                            if showClientSecret {
                                TextField("Client secret", text: Binding(
                                    get: { service.clientSecret },
                                    set: { service.clientSecret = $0 }
                                ))
                            } else {
                                SecureField("Client secret", text: Binding(
                                    get: { service.clientSecret },
                                    set: { service.clientSecret = $0 }
                                ))
                            }
                        }
                        Button {
                            showClientSecret.toggle()
                        } label: {
                            Image(systemName: showClientSecret ? "eye.slash" : "eye")
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("toggleClientSecretVisibility")
                        .accessibilityLabel(showClientSecret ? "Hide client secret" : "Show client secret")
                    }
                    TextField("Redirect URI", text: Binding(
                        get: { service.redirectURI },
                        set: { service.redirectURI = $0 }
                    ))
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    TextField("Location ID", text: Binding(
                        get: { service.locationID },
                        set: { service.locationID = $0 }
                    ))
                    TextField("Fulfillment (dth/csp/ais/sth)", text: Binding(
                        get: { service.fulfillment },
                        set: { service.fulfillment = $0 }
                    ))
                }
            }
            .navigationTitle("Settings")
            .alert("Kroger sign-in", isPresented: Binding(
                get: { authError != nil },
                set: { if !$0 { authError = nil } }
            )) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(authError ?? "")
            }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
