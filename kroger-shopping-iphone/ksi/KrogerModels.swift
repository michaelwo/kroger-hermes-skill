import Foundation

struct KrogerProduct: Identifiable, Hashable, Codable {
    let id: String
    let upc: String
    let description: String
    let brand: String?
    let size: String?
    let price: Double?
    let unitPrice: Double?
    let unitPriceLabel: String?
    let outOfStock: Bool
    let previouslyPurchased: Bool
    let latestPurchaseDate: String?
    let unwantedIngredients: [String]
    let unwantedIngredientCount: Int?
    
    var displayPrice: String {
        guard let price else { return "Price unavailable" }
        return price.formatted(.currency(code: "USD"))
    }
    
    var displaySize: String {
        size ?? "Size unavailable"
    }

    var displayUnitPrice: String {
        guard let unitPrice else { return "Unavailable" }
        return unitPrice.formatted(.currency(code: "USD")) + "/\(unitPriceLabel ?? "unit")"
    }

    var displayUnwantedCount: String {
        unwantedIngredientCount.map(String.init) ?? "Unknown"
    }

    var preferenceSummary: String {
        if let unwantedIngredientCount {
            if !unwantedIngredients.isEmpty {
                return "Contains: " + unwantedIngredients.joined(separator: ", ")
            }
            return unwantedIngredientCount == 0
                ? "No unwanted ingredients"
                : "Unwanted ingredients identified"
        }
        return previouslyPurchased ? "Previously purchased" : "Ingredients not assessed"
    }
}

struct KrogerAPIError: LocalizedError {
    let message: String
    
    var errorDescription: String? { message }
}

struct KrogerTokenResponse: Decodable {
    let accessToken: String
    let expiresIn: TimeInterval?
    let refreshToken: String?
    
    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case expiresIn = "expires_in"
        case refreshToken = "refresh_token"
    }
}

struct KrogerProductsResponse: Decodable {
    let data: [KrogerProductPayload]
}

struct KrogerProductPayload: Decodable {
    let productId: String?
    let upc: String?
    let description: String?
    let brand: String?
    let items: [KrogerItemPayload]?
    
    enum CodingKeys: String, CodingKey {
        case productId = "productId"
        case upc
        case description
        case brand
        case items
    }
}

struct KrogerItemPayload: Decodable {
    let size: String?
    let price: KrogerPricePayload?
    let inventory: KrogerInventoryPayload?
    
    struct KrogerPricePayload: Decodable {
        let regular: Double?
        let regularPerUnitEstimate: Double?
        
        enum CodingKeys: String, CodingKey {
            case regular
            case regularPerUnitEstimate = "regularPerUnitEstimate"
        }
    }
    
    struct KrogerInventoryPayload: Decodable {
        let stockLevel: String?
        
        enum CodingKeys: String, CodingKey {
            case stockLevel = "stockLevel"
        }
    }
}

struct KrogerDetailResponse: Decodable {
    let data: KrogerProductPayload
}

struct KrogerAddRequest: Encodable {
    let items: [Item]
    
    struct Item: Encodable {
        let upc: String
        let quantity: Int
        let modality: String
    }
}
