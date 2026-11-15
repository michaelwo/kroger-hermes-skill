import AuthenticationServices
import Combine
import Foundation
import OSLog
import UIKit

@MainActor
final class KrogerService: NSObject, ObservableObject, ASWebAuthenticationPresentationContextProviding {
    @Published private(set) var isLoading = false
    @Published private(set) var isAuthenticated = false
    let receiptIndex: ReceiptIndex

    private let baseURL = URL(string: "https://api.kroger.com")!
    private let defaults = UserDefaults.standard
    private var appToken: String?
    private var appTokenExpiresAt: Date?
    private var authSession: ASWebAuthenticationSession?
    private let logger = Logger(subsystem: "ksi", category: "KrogerAPI")

    override init() {
        receiptIndex = ReceiptLoader.load()
        super.init()
        isAuthenticated = KeychainStore.load("kroger.accessToken") != nil
    }

    var clientID: String {
        get {
            if let value = environmentValue("KROGER_IPHONE_CLIENT_ID") { return value }
            if let value = environmentValue("KROGER_CLIENT_ID") { return value }
            if let value = KeychainStore.load("kroger.clientID") { return value }
            return defaults.string(forKey: "kroger.clientID") ?? ""
        }
        set {
            try? KeychainStore.save(newValue, for: "kroger.clientID")
            defaults.removeObject(forKey: "kroger.clientID")
        }
    }

    var clientSecret: String {
        get {
            if let value = environmentValue("KROGER_IPHONE_CLIENT_SECRET") { return value }
            if let value = environmentValue("KROGER_CLIENT_SECRET") { return value }
            if let value = KeychainStore.load("kroger.clientSecret") { return value }
            return defaults.string(forKey: "kroger.clientSecret") ?? ""
        }
        set {
            try? KeychainStore.save(newValue, for: "kroger.clientSecret")
            defaults.removeObject(forKey: "kroger.clientSecret")
        }
    }

    var locationID: String {
        get { defaults.string(forKey: "kroger.locationID") ?? "02100998" }
        set { defaults.set(newValue, forKey: "kroger.locationID") }
    }

    var fulfillment: String {
        get { defaults.string(forKey: "kroger.fulfillment") ?? "dth" }
        set { defaults.set(newValue, forKey: "kroger.fulfillment") }
    }

    var redirectURI: String {
        get { defaults.string(forKey: "kroger.redirectURI") ?? "kroger-personal://oauth/callback" }
        set { defaults.set(newValue, forKey: "kroger.redirectURI") }
    }

    func recommend(query: String, limit: Int = 10) async throws -> [KrogerProduct] {
        isLoading = true
        defer { isLoading = false }
        logger.info("Starting recommendation query")
        let products = try await search(query: query, limit: min(max(limit, 1), 25))
        let ranked = products.enumerated().sorted { left, right in
            let lhs = left.element
            let rhs = right.element

            if lhs.previouslyPurchased != rhs.previouslyPurchased {
                return lhs.previouslyPurchased
            }

            let lhsCount = lhs.unwantedIngredientCount
            let rhsCount = rhs.unwantedIngredientCount
            if (lhsCount != nil) != (rhsCount != nil) {
                return lhsCount != nil
            }
            if let lhsCount, let rhsCount, lhsCount != rhsCount {
                return lhsCount < rhsCount
            }

            if (lhs.unitPrice != nil) != (rhs.unitPrice != nil) {
                return lhs.unitPrice != nil
            }
            if let lhsUnitPrice = lhs.unitPrice,
               let rhsUnitPrice = rhs.unitPrice,
               lhsUnitPrice != rhsUnitPrice {
                return lhsUnitPrice < rhsUnitPrice
            }

            return left.offset < right.offset
        }

        return ranked.prefix(limit).map(\.element)
    }

    func search(query: String, limit: Int = 10) async throws -> [KrogerProduct] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            throw KrogerAPIError(message: "Enter a product to search for.")
        }
        guard !normalizedClientID.isEmpty, !normalizedClientSecret.isEmpty else {
            throw KrogerAPIError(message: "Add your Kroger API credentials in Settings.")
        }

        var components = URLComponents(
            url: baseURL.appendingPathComponent("/v1/products"),
            resolvingAgainstBaseURL: false
        )!
        components.queryItems = [
            URLQueryItem(name: "filter.term", value: trimmed),
            URLQueryItem(name: "filter.limit", value: String(limit)),
            URLQueryItem(name: "filter.locationId", value: locationID.trimmingCharacters(in: .whitespacesAndNewlines)),
            URLQueryItem(name: "filter.fulfillment", value: fulfillment.trimmingCharacters(in: .whitespacesAndNewlines))
        ]

        let request = try await authorizedRequest(method: "GET", url: components.url!, userToken: false)
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            logger.error("Product request transport failed: \(error.localizedDescription, privacy: .public)")
            throw KrogerAPIError(message: "Could not reach Kroger: \(error.localizedDescription)")
        }
        try validate(response: response, data: data, stage: "product search")

        do {
            let payload = try JSONDecoder().decode(KrogerProductsResponse.self, from: data)
            let products: [KrogerProduct] = payload.data.compactMap { item -> KrogerProduct? in
                guard let upc = item.upc, let description = item.description else { return nil }
                let firstItem = item.items?.first
                return KrogerProduct(
                    id: item.productId ?? upc,
                    upc: upc,
                    description: description,
                    brand: item.brand,
                    size: firstItem?.size,
                    price: firstItem?.price?.regular,
                    unitPrice: firstItem?.price?.regularPerUnitEstimate,
                    unitPriceLabel: nil,
                    outOfStock: firstItem?.inventory?.stockLevel == "TEMPORARILY_OUT_OF_STOCK",
                    previouslyPurchased: ReceiptIndex.normalizeUPC(upc).map { receiptIndex.purchasedUPCs.contains($0) } ?? false,
                    latestPurchaseDate: ReceiptIndex.normalizeUPC(upc).flatMap { receiptIndex.latestPurchaseDateByUPC[$0] },
                    unwantedIngredients: [],
                    unwantedIngredientCount: nil
                )
            }
            return await enrich(products)
        } catch {
            logger.error("Product response decoding failed: \(error.localizedDescription, privacy: .public)")
            throw KrogerAPIError(message: "Kroger returned an unexpected product response.")
        }
    }

    private func enrich(_ products: [KrogerProduct]) async -> [KrogerProduct] {
        var enriched: [KrogerProduct] = []
        for product in products {
            enriched.append(await enrichedProduct(product))
        }
        return enriched
    }

    private func enrichedProduct(_ product: KrogerProduct) async -> KrogerProduct {
        do {
            var components = URLComponents(
                url: baseURL.appendingPathComponent("/v1/products/\(product.id)"),
                resolvingAgainstBaseURL: false
            )!
            components.queryItems = [
                URLQueryItem(name: "filter.locationId", value: locationID.trimmingCharacters(in: .whitespacesAndNewlines))
            ]
            let request = try await authorizedRequest(method: "GET", url: components.url!, userToken: false)
            let (data, response) = try await URLSession.shared.data(for: request)
            try validate(response: response, data: data, stage: "product detail")
            let detail = try JSONDecoder().decode(KrogerDetailResponse.self, from: data).data
            let raw = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let detailRaw = (raw?["data"] as? [String: Any]) ?? raw
            let item = detail.items?.first
            let ingredientText = ingredientText(from: detailRaw)
            let matches = ingredientText.map(unwantedMatches(in:)) 
            let computedUnit = computedUnitPrice(
                price: item?.price?.regular ?? product.price,
                size: item?.size ?? product.size
            )
            let unitPrice = product.unitPrice ?? item?.price?.regularPerUnitEstimate ?? computedUnit?.price
            let unitLabel = computedUnit?.label
            return KrogerProduct(
                id: product.id,
                upc: product.upc,
                description: product.description,
                brand: product.brand,
                size: item?.size ?? product.size,
                price: item?.price?.regular ?? product.price,
                unitPrice: unitPrice,
                unitPriceLabel: unitLabel,
                outOfStock: item?.inventory?.stockLevel == "TEMPORARILY_OUT_OF_STOCK" || product.outOfStock,
                previouslyPurchased: product.previouslyPurchased || (ReceiptIndex.normalizeUPC(product.upc).map { receiptIndex.purchasedUPCs.contains($0) } ?? false),
                latestPurchaseDate: product.latestPurchaseDate ?? ReceiptIndex.normalizeUPC(product.upc).flatMap { receiptIndex.latestPurchaseDateByUPC[$0] },
                unwantedIngredients: matches?.map(\.label) ?? [],
                unwantedIngredientCount: matches?.count
            )
        } catch {
            logger.debug("Product detail enrichment skipped: \(error.localizedDescription, privacy: .public)")
            return product
        }
    }

    private func ingredientText(from raw: [String: Any]?) -> String? {
        guard let raw else { return nil }
        let values = [raw["nutritionInformation"], raw["nutrition"]].compactMap { $0 }
        var statements: [String] = []
        func visit(_ value: Any) {
            if let dictionary = value as? [String: Any] {
                for (key, nested) in dictionary {
                    if key.localizedCaseInsensitiveContains("ingredient") {
                        if let text = nested as? String, !text.isEmpty { statements.append(text) }
                    }
                    visit(nested)
                }
            } else if let array = value as? [Any] {
                array.forEach(visit)
            }
        }
        values.forEach(visit)
        let result = statements.joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines)
        return result.isEmpty ? nil : result
    }

    private func unwantedMatches(in text: String) -> [(label: String, keyword: String)] {
        let rules: [(String, String)] = [
            ("acesulfame k", "Acesulfame-K"), ("aspartame", "Aspartame"),
            ("artificial colors", "Artificial colors"), ("red 40", "Artificial colors"),
            ("yellow 5", "Artificial colors"), ("yellow 6", "Artificial colors"),
            ("artificial flavors", "Artificial flavors"), ("bha", "BHA"),
            ("bht", "BHT"), ("benzoates", "Benzoates in food"),
            ("brominated vegetable oil", "Brominated vegetable oil (BVO)"),
            ("bvo", "Brominated vegetable oil (BVO)"), ("carmine", "Carmine"),
            ("datem", "DATEM"), ("edta", "EDTA"), ("high fructose corn syrup", "High-fructose corn syrup"),
            ("hydrogenated", "Hydrogenated/partially hydrogenated fats & oils"),
            ("monosodium glutamate", "Monosodium glutamate (MSG)"), ("msg", "Monosodium glutamate (MSG)"),
            ("nitrate", "Nitrates/nitrites"), ("nitrite", "Nitrates/nitrites"),
            ("parabens", "Parabens"), ("polydextrose", "Polydextrose"),
            ("propionate", "Propionates"), ("saccharin", "Saccharin"),
            ("sucralose", "Sucralose"), ("sulfite", "Sulfites"), ("sulfur dioxide", "Sulfites"),
            ("tbhq", "TBHQ"), ("trans fatty acids", "Trans fatty acids"),
            ("vanillin", "Vanillin, synthetic"), ("synthetic vanillin", "Vanillin, synthetic"),
            ("canola oil", "Seed oils"), ("corn oil", "Seed oils"), ("cottonseed oil", "Seed oils"),
            ("palm kernel oil", "Seed oils"), ("soybean oil", "Seed oils"), ("sunflower oil", "Seed oils")
        ]
        let normalized = " " + text.lowercased()
            .replacingOccurrences(of: "&", with: " ")
            .replacingOccurrences(of: ",", with: " ")
            .replacingOccurrences(of: ".", with: " ")
            .replacingOccurrences(of: "(", with: " ")
            .replacingOccurrences(of: ")", with: " ")
            .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
            .joined(separator: " ") + " "
        var found: [String: (label: String, keyword: String)] = [:]
        for (keyword, label) in rules {
            let normalizedKeyword = " " + keyword.replacingOccurrences(of: "-", with: " ") + " "
            if normalized.contains(normalizedKeyword) {
                found[label] = (label, keyword)
            }
        }
        return found.values.sorted { $0.label < $1.label }
    }

    private func computedUnitPrice(price: Double?, size: String?) -> (price: Double, label: String)? {
        guard let price, price > 0, var normalized = size?.lowercased() else { return nil }
        normalized = normalized.replacingOccurrences(of: "half gallon", with: "64 fl oz")
        normalized = normalized.replacingOccurrences(of: "1/2 gallon", with: "64 fl oz")
        normalized = normalized.replacingOccurrences(of: "1/2 gal", with: "64 fl oz")
        let pattern = #"([0-9]+(?:\.[0-9]+)?)\s*(fl oz|fluid ounces?|oz|lbs?|lb|gallons?|gal|quarts?|qt|pints?|pt|counts?|ct)"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: normalized, range: NSRange(normalized.startIndex..., in: normalized)),
              let quantityRange = Range(match.range(at: 1), in: normalized),
              let unitRange = Range(match.range(at: 2), in: normalized),
              let quantity = Double(normalized[quantityRange]) else { return nil }
        let rawUnit = String(normalized[unitRange])
        let conversion: (amount: Double, label: String)
        switch rawUnit {
        case "gallon", "gallons", "gal": conversion = (quantity * 128, "fl oz")
        case "quart", "quarts", "qt": conversion = (quantity * 32, "fl oz")
        case "pint", "pints", "pt": conversion = (quantity * 16, "fl oz")
        case "lb", "lbs": conversion = (quantity * 16, "oz")
        default: conversion = (quantity, rawUnit.hasPrefix("count") || rawUnit == "ct" ? "ct" : rawUnit)
        }
        guard conversion.amount > 0 else { return nil }
        return (price / conversion.amount, conversion.label)
    }

    func login() async throws {
        guard !normalizedClientID.isEmpty, !normalizedClientSecret.isEmpty else {
            throw KrogerAPIError(message: "Add your Kroger API credentials in Settings first.")
        }
        guard let redirect = URL(string: redirectURI),
              let callbackScheme = redirect.scheme,
              callbackScheme == "kroger-personal" else {
            throw KrogerAPIError(message: "Redirect URI must be kroger-personal://oauth/callback.")
        }

        var components = URLComponents(string: "https://api.kroger.com/v1/connect/oauth2/authorize")!
        components.queryItems = [
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "client_id", value: normalizedClientID),
            URLQueryItem(name: "redirect_uri", value: redirectURI.trimmingCharacters(in: .whitespacesAndNewlines)),
            URLQueryItem(name: "scope", value: "product.compact cart.basic:write profile.compact"),
            URLQueryItem(name: "state", value: UUID().uuidString)
        ]

        guard let authorizationURL = components.url else {
            throw KrogerAPIError(message: "Could not create the Kroger authorization URL.")
        }

        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            let session = ASWebAuthenticationSession(
                url: authorizationURL,
                callbackURLScheme: callbackScheme
            ) { [weak self] callbackURL, error in
                Task { @MainActor in
                    guard let self else {
                        continuation.resume(throwing: KrogerAPIError(message: "Kroger login was interrupted."))
                        return
                    }
                    self.authSession = nil
                    if let error {
                        continuation.resume(throwing: KrogerAPIError(message: "Kroger login failed: \(error.localizedDescription)"))
                        return
                    }
                    guard let callbackURL else {
                        continuation.resume(throwing: KrogerAPIError(message: "Kroger did not return a login callback."))
                        return
                    }
                    do {
                        try await self.exchangeAuthorizationCode(from: callbackURL)
                        self.isAuthenticated = true
                        continuation.resume(returning: ())
                    } catch {
                        continuation.resume(throwing: error)
                    }
                }
            }
            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = false
            authSession = session
            guard session.start() else {
                authSession = nil
                continuation.resume(throwing: KrogerAPIError(message: "Could not start Kroger login."))
                return
            }
        }
    }

    func logout() {
        KeychainStore.delete("kroger.accessToken")
        KeychainStore.delete("kroger.refreshToken")
        KeychainStore.delete("kroger.accessTokenExpiry")
        isAuthenticated = false
    }

    func add(upc: String, quantity: Int, modality: String = "PICKUP") async throws {
        guard quantity > 0 else {
            throw KrogerAPIError(message: "Quantity must be a whole number greater than zero.")
        }
        guard upc.count == 13, upc.allSatisfy(\.isNumber) else {
            throw KrogerAPIError(message: "UPC must be a 13-digit number.")
        }
        guard modality == "PICKUP" || modality == "DELIVERY" else {
            throw KrogerAPIError(message: "Modality must be PICKUP or DELIVERY.")
        }

        var request = try await authorizedRequest(
            method: "PUT",
            url: baseURL.appendingPathComponent("/v1/cart/add"),
            userToken: true
        )
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(
            KrogerAddRequest(items: [.init(upc: upc, quantity: quantity, modality: modality)])
        )

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw KrogerAPIError(message: "Could not reach Kroger's cart service: \(error.localizedDescription)")
        }
        try validate(response: response, data: data, stage: "cart add")
    }

    private func exchangeAuthorizationCode(from callbackURL: URL) async throws {
        guard let components = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false) else {
            throw KrogerAPIError(message: "Kroger returned an invalid login callback.")
        }
        if let error = components.queryItems?.first(where: { $0.name == "error" })?.value {
            let description = components.queryItems?.first(where: { $0.name == "error_description" })?.value ?? error
            throw KrogerAPIError(message: "Kroger login was not approved: \(description)")
        }
        guard let code = components.queryItems?.first(where: { $0.name == "code" })?.value else {
            throw KrogerAPIError(message: "Kroger callback did not contain an authorization code.")
        }

        let body = formBody([
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirectURI.trimmingCharacters(in: .whitespacesAndNewlines)
        ])
        let response = try await postToken(body: body, stage: "authorization code exchange")
        let token = try decodeToken(response.data)
        try saveUserToken(token)
    }

    private func refreshUserToken() async throws -> String {
        guard let refreshToken = KeychainStore.load("kroger.refreshToken") else {
            throw KrogerAPIError(message: "Kroger sign-in has expired. Sign in again.")
        }
        let body = formBody([
            "grant_type": "refresh_token",
            "refresh_token": refreshToken
        ])
        let response = try await postToken(body: body, stage: "token refresh")
        let token = try decodeToken(response.data, fallbackRefreshToken: refreshToken)
        try saveUserToken(token)
        return token.accessToken
    }

    private func token(forUser: Bool) async throws -> String {
        if forUser {
            if let token = KeychainStore.load("kroger.accessToken"),
               let expiryText = KeychainStore.load("kroger.accessTokenExpiry"),
               let expiry = TimeInterval(expiryText),
               expiry > Date().timeIntervalSince1970 + 60 {
                return token
            }
            return try await refreshUserToken()
        }

        if let appToken, let expiry = appTokenExpiresAt,
           expiry > Date().addingTimeInterval(60) {
            return appToken
        }

        let body = formBody([
            "grant_type": "client_credentials",
            "scope": "product.compact"
        ])
        let response = try await postToken(body: body, stage: "token request")
        let token = try decodeToken(response.data)
        appToken = token.accessToken
        appTokenExpiresAt = Date().addingTimeInterval(token.expiresIn ?? 1800)
        return token.accessToken
    }

    private func authorizedRequest(method: String, url: URL, userToken: Bool) async throws -> URLRequest {
        let token = try await token(forUser: userToken)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return request
    }

    private func postToken(body: Data, stage: String) async throws -> (data: Data, response: URLResponse) {
        var request = URLRequest(url: baseURL.appendingPathComponent("/v1/connect/oauth2/token"))
        request.httpMethod = "POST"
        let credentials = Data("\(normalizedClientID):\(normalizedClientSecret)".utf8).base64EncodedString()
        request.setValue("Basic \(credentials)", forHTTPHeaderField: "Authorization")
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = body

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            try validate(response: response, data: data, stage: stage)
            return (data, response)
        } catch let error as KrogerAPIError {
            throw error
        } catch {
            logger.error("\(stage) transport failed: \(error.localizedDescription, privacy: .public)")
            throw KrogerAPIError(message: "Could not reach Kroger's token service: \(error.localizedDescription)")
        }
    }

    private func decodeToken(_ data: Data, fallbackRefreshToken: String? = nil) throws -> KrogerTokenResponse {
        do {
            var token = try JSONDecoder().decode(KrogerTokenResponse.self, from: data)
            token = KrogerTokenResponse(
                accessToken: token.accessToken,
                expiresIn: token.expiresIn,
                refreshToken: token.refreshToken ?? fallbackRefreshToken
            )
            return token
        } catch {
            logger.error("Token response decoding failed: \(error.localizedDescription, privacy: .public)")
            throw KrogerAPIError(message: "Kroger returned an unexpected token response.")
        }
    }

    private func saveUserToken(_ token: KrogerTokenResponse) throws {
        try KeychainStore.save(token.accessToken, for: "kroger.accessToken")
        if let refresh = token.refreshToken {
            try KeychainStore.save(refresh, for: "kroger.refreshToken")
        }
        let expiry = Date().timeIntervalSince1970 + (token.expiresIn ?? 1800)
        try KeychainStore.save(String(expiry), for: "kroger.accessTokenExpiry")
    }

    private func environmentValue(_ name: String) -> String? {
        let value = ProcessInfo.processInfo.environment[name]?.trimmingCharacters(in: .whitespacesAndNewlines)
        return value?.isEmpty == false ? value : nil
    }

    private var normalizedClientID: String {
        clientID.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var normalizedClientSecret: String {
        clientSecret.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func formBody(_ values: [String: String]) -> Data {
        var components = URLComponents()
        components.queryItems = values.map { URLQueryItem(name: $0.key, value: $0.value) }
        return Data((components.percentEncodedQuery ?? "").utf8)
    }

    private func validate(response: URLResponse, data: Data, stage: String) throws {
        guard let http = response as? HTTPURLResponse else {
            throw KrogerAPIError(message: "Kroger returned an invalid response.")
        }
        guard (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? "No response body"
            logger.error("\(stage) failed with HTTP \(http.statusCode)")
            throw KrogerAPIError(message: "Kroger \(stage) failed (\(http.statusCode)): \(body)")
        }
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap(\.windows)
            .first(where: \.isKeyWindow) ?? ASPresentationAnchor()
    }
}
