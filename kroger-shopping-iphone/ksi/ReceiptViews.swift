import SwiftUI

struct ReceiptsView: View {
    let index: ReceiptIndex
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Group {
                if index.orders.isEmpty {
                    ContentUnavailableView(
                        "Receipt data unavailable",
                        systemImage: "receipt",
                        description: Text("No bundled purchase history could be loaded.")
                    )
                } else {
                    List(index.orders) { order in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text(order.displayDate)
                                    .font(.headline)
                                Spacer()
                                Text(order.total ?? "Unavailable")
                                    .font(.headline)
                            }
                            Text("Order \(order.displayNumber)")
                                .font(.subheadline)
                            HStack {
                                Text(order.purchaseType ?? "Unavailable")
                                Text("·")
                                Text("\(order.upcs.count) products")
                                Spacer()
                                Text(order.status ?? "Unavailable")
                            }
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
            .navigationTitle("Receipts")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

struct BuyAgainView: View {
    let index: ReceiptIndex
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Group {
                if index.buyAgain.isEmpty {
                    ContentUnavailableView(
                        "Nothing to buy again",
                        systemImage: "cart",
                        description: Text("Receipt purchases will appear here.")
                    )
                } else {
                    List(index.buyAgain) { purchase in
                        VStack(alignment: .leading, spacing: 5) {
                            Text(purchase.displayName)
                                .font(.headline)
                            Text("UPC \(purchase.upc)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            HStack {
                                Text("Purchased \(purchase.count) time\(purchase.count == 1 ? "" : "s")")
                                Spacer()
                                Text("Last \(purchase.latestDate)")
                            }
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
            .navigationTitle("Buy Again")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
