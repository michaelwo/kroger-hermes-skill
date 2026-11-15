import XCTest

final class KrogerShoppingUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()

        guard let clientID = ProcessInfo.processInfo.environment["KROGER_IPHONE_CLIENT_ID"],
              let clientSecret = ProcessInfo.processInfo.environment["KROGER_IPHONE_CLIENT_SECRET"],
              !clientID.isEmpty,
              !clientSecret.isEmpty else {
            throw XCTSkip("Set KROGER_IPHONE_CLIENT_ID and KROGER_IPHONE_CLIENT_SECRET to run the live Kroger smoke test.")
        }

        app.launchEnvironment["KROGER_IPHONE_CLIENT_ID"] = clientID
        app.launchEnvironment["KROGER_IPHONE_CLIENT_SECRET"] = clientSecret
    }

    @MainActor
    func testPeanutButterSearchShowsRecommendationMetadata() throws {
        app.launch()

        let searchField = app.searchFields.firstMatch
        XCTAssertTrue(searchField.waitForExistence(timeout: 10))
        searchField.tap()
        searchField.typeText("peanut butter")

        searchField.typeText("\n")

        let unitPrice = app.descendants(matching: .any)
            .matching(identifier: "unitPriceLabel")
            .firstMatch
        XCTAssertTrue(unitPrice.waitForExistence(timeout: 45))
        XCTAssertFalse(unitPrice.label.contains("Unavailable"))

        let unwantedCount = app.descendants(matching: .any)
            .matching(identifier: "unwantedCountLabel")
            .firstMatch
        XCTAssertTrue(unwantedCount.exists)

        let preferenceSummary = app.descendants(matching: .any)
            .matching(identifier: "preferenceSummaryLabel")
            .firstMatch
        XCTAssertTrue(preferenceSummary.exists)
    }
}
