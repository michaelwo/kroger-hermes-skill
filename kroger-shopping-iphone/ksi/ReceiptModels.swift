import Foundation

struct PurchaseHistory: Codable {
    let source: String?
    let fetchedAt: String?
    let pageTotal: Int?
    let orders: [PurchaseOrder]
}

struct PurchaseOrder: Codable, Identifiable {
    let receiptKey: String?
    let orderDate: String?
    let createdDateTime: String?
    let purchaseType: String?
    let total: String?
    let status: String?
    let handoffStoreId: String?
    let fulfillmentPartner: String?
    let upcs: [String]
    let productNames: [String: String]?

    var id: String { receiptKey ?? createdDateTime ?? UUID().uuidString }
    var displayDate: String { orderDate ?? "Unavailable" }
    var displayNumber: String {
        guard let receiptKey, let number = receiptKey.split(separator: "~").last else {
            return "Unavailable"
        }
        return String(number)
    }
}

struct PurchaseRecord: Identifiable, Hashable {
    let upc: String
    let name: String?
    let count: Int
    let latestDate: String

    var id: String { upc }
    var displayName: String { name ?? "Name unavailable" }
}

struct ReceiptIndex {
    let history: PurchaseHistory?
    let orders: [PurchaseOrder]
    let purchasedUPCs: Set<String>
    let latestPurchaseDateByUPC: [String: String]
    let purchaseNamesByUPC: [String: String]
    let purchaseCountsByUPC: [String: Int]

    var buyAgain: [PurchaseRecord] {
        purchasedUPCs.map { upc in
            PurchaseRecord(
                upc: upc,
                name: purchaseNamesByUPC[upc],
                count: purchaseCountsByUPC[upc, default: 0],
                latestDate: latestPurchaseDateByUPC[upc] ?? "Unavailable"
            )
        }
        .sorted {
            if $0.latestDate != $1.latestDate { return $0.latestDate > $1.latestDate }
            return $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending
        }
    }

    static let empty = ReceiptIndex(
        history: nil,
        orders: [],
        purchasedUPCs: [],
        latestPurchaseDateByUPC: [:],
        purchaseNamesByUPC: [:],
        purchaseCountsByUPC: [:]
    )

    static func make(from history: PurchaseHistory?) -> ReceiptIndex {
        guard let history else { return .empty }
        var upcs = Set<String>()
        var latest: [String: String] = [:]
        var names: [String: String] = [:]
        var counts: [String: Int] = [:]

        for order in history.orders {
            let normalized = Set(order.upcs.compactMap(Self.normalizeUPC))
            for upc in normalized {
                upcs.insert(upc)
                counts[upc, default: 0] += 1
                if let date = order.orderDate, date > (latest[upc] ?? "") {
                    latest[upc] = date
                }
                if names[upc] == nil,
                   let rawName = order.productNames?.first(where: { normalizeUPC($0.key) == upc })?.value,
                   !rawName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    names[upc] = rawName
                }
            }
        }
        return ReceiptIndex(
            history: history,
            orders: history.orders,
            purchasedUPCs: upcs,
            latestPurchaseDateByUPC: latest,
            purchaseNamesByUPC: names,
            purchaseCountsByUPC: counts
        )
    }

    static func normalizeUPC(_ value: String) -> String? {
        let digits = value.filter(\.isNumber)
        guard !digits.isEmpty, digits.count <= 13 else { return nil }
        return String(repeating: "0", count: 13 - digits.count) + digits
    }
}

enum ReceiptLoader {
    static func load() -> ReceiptIndex {
        guard let url = Bundle.main.url(forResource: "purchase-history", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let history = try? JSONDecoder().decode(PurchaseHistory.self, from: data) else {
            return .empty
        }
        return ReceiptIndex.make(from: history)
    }
}
