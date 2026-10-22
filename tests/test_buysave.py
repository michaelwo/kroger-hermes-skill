from kroger_shopping.buysave import Event, format_report, pick_event, shop_all_keyword
from kroger_shopping.clipcoupon import Purchase


SHOP_ALL = (
    "https://www.kroger.com/search?keyword=Buy5Save1ShopAll26P9W4Central"
    "&query=Buy5Save1ShopAll26P9W4Central&searchType=mktg%20attribute"
    "&monet=curated&fulfillment=all&pzn=relevance"
)


def test_shop_all_keyword_ignores_sponsored_links():
    assert shop_all_keyword(SHOP_ALL) == "Buy5Save1ShopAll26P9W4Central"
    sponsored = SHOP_ALL.replace("monet=curated", "monet=false")
    assert shop_all_keyword(sponsored) is None
    assert shop_all_keyword("https://www.kroger.com/products/my-sale-items") is None


def test_pick_event_uses_the_mega_event_not_another_offer():
    products = [{
        "offers": [
            {"displayTemplate": "STANDARD", "offerCode": "other", "defaultDescription": "Save $2"},
            {
                "displayTemplate": "MEGA_EVENT",
                "offerCode": "3ca57467-371b-49a1-9fd5-2c0e5ca5b7b0",
                "defaultDescription": "Save $1 each when you buy 5 or more",
                "end": "2026-10-27T23:59:59",
            },
        ]
    }]
    event = pick_event(products)
    assert event is not None
    assert event.offer_code == "3ca57467-371b-49a1-9fd5-2c0e5ca5b7b0"
    assert event.description.startswith("Save $1 each")
    assert pick_event([{"offers": [{"displayTemplate": "STANDARD", "offerCode": "x"}]}]) is None


def test_report_sorts_by_count_then_date_and_includes_upc():
    event = Event("code", "Save $1 each when you buy 5 or more", "2026-10-27T23:59:59")
    purchases = [
        Purchase("0002100061223", "Philadelphia Original Cream Cheese Brick, 8 oz", 4, "2026-10-11"),
        Purchase("0001376402801", "Dave's Killer Bread Plain Awesome Bagels", 2, "2026-10-11"),
        Purchase("0005410000060", "", 1, "2026-03-28"),
    ]
    hits = [
        {"upc": "0005410000060", "description": "Vlasic Kosher Dill Pickle Spears"},
        {"upc": "0001376402801", "description": "ignored when history has a name"},
        {"upc": "0002100061223", "description": "Philadelphia"},
        {"upc": "0000000000000", "description": "not in history"},
    ]
    text = format_report(event, purchases, hits, 0)
    assert text.splitlines()[:2] == [
        "Save $1 each when you buy 5 or more  exp 2026-10-27",
        "history 3  matched 3  lookup failures 0",
    ]
    body = text.splitlines()[3:]
    assert body[0].startswith("4  2026-10-11  0002100061223  Philadelphia")
    assert body[1].startswith("2  2026-10-11  0001376402801")
    assert body[2] == "1  2026-03-28  0005410000060  Vlasic Kosher Dill Pickle Spears"
    assert "0000000000000" not in text
