from kroger_shopping.clipcoupon import Coupon, Purchase, format_dry_run, hits_for, is_candidate


def _coupon(**overrides) -> Coupon:
    data = dict(
        id="1",
        offer_id="offer-1",
        brand="illy",
        short="Save $3.00 on illy Coffee",
        requirement="when you buy ONE (1) illy Coffee or Espresso item",
        expiration="2026-11-01T23:59:00Z",
        savings=3,
        added=False,
        requirement_ids=("9",),
        coupon_type="STANDARD",
    )
    data.update(overrides)
    return Coupon(**data)


def _buy(upc="0073341100009", name="Illy Classico Whole Bean Coffee, 8.8 oz", count=1, last="2025-12-22"):
    return Purchase(upc, name, count, last)


def test_illy_title_and_upc_is_a_hit():
    coupon = _coupon()
    bought = [_buy()]
    assert is_candidate(coupon, bought)
    found = hits_for([coupon], {"offer-1": {"0073341100009"}}, bought)
    assert found[0].purchases[0].upc == "0073341100009"


def test_title_hit_without_upc_does_not_clip():
    coupon = _coupon(
        id="4251385",
        offer_id="potatoes",
        brand="Kroger Brand",
        short="Save $1.20 on 2 Kroger Brand Frozen Potatoes or Onion Rings",
        requirement="when you buy TWO (2) Kroger Brand Frozen Potatoes or Onion Rings",
    )
    bought = [_buy("0001111091754", "Kroger Russet Potatoes Bag, 10 lb", 2, "2026-10-11")]
    assert is_candidate(coupon, bought)
    assert hits_for([coupon], {"potatoes": {"0001111099999"}}, bought) == []


def test_generic_candy_token_is_not_a_candidate():
    coupon = _coupon(
        brand="TWIX",
        short="$0.99 Mars Candy",
        requirement="When You Buy ONE (1) M&Ms, Snickers, Skittles, Twix, or Starburst",
    )
    bought = [_buy("0002430004120", "Little Debbie Nutty Buddy Peanut Butter Wafer Bars", 1, "2026-08-16")]
    assert not is_candidate(coupon, bought)


def test_requirement_subbrand_is_a_candidate():
    coupon = _coupon(
        brand="General Mills",
        short="SAVE $0.50 on 2 General Mills Snack Bars",
        requirement="when you buy TWO (2) BOXES Nature Valley, Fiber One, or Larabar Bars",
    )
    bought = [_buy("0001600043268", "Nature Valley Crunchy Oats and Honey Granola, 16 oz")]
    assert is_candidate(coupon, bought)


def test_unnamed_fee_upc_does_not_clip():
    coupon = _coupon(
        brand="Larabar",
        short="Save 20% on Larabar Minis 20ct PICKUP OR DELIVERY ONLY",
        requirement="When you buy ONE Larabar Minis on PICKUP OR DELIVERY ONLY",
    )
    named = _buy("0001111014114", "Simple Truth Organic Oats and Honey Granola, 22 oz")
    fee = Purchase("0000000080208", "", 4, "2026-10-21")
    assert hits_for([coupon], {coupon.offer_id: {"0000000080208"}}, [named, fee]) == []
    coupon = _coupon(short="$6.99 Peet's Coffee", brand="Peet's Coffee and Tea")
    bought = [_buy("0078535702350", "Peet's Major Dickason's Blend Dark Roast Ground Coffee, 10.5 oz", 4, "2026-01-24")]
    found = hits_for([coupon], {coupon.offer_id: {"0078535702350"}}, bought)
    text = format_dry_run(214, 40, found, 0, 12.5)
    assert "PRICE" in text
    assert "Nothing was clipped." in text
    assert "Would clip 1." in text


def test_clip_report_marks_failures_and_says_what_was_clipped():
    from kroger_shopping.clipcoupon import format_clip

    coupon = _coupon()
    bought = [_buy()]
    found = hits_for([coupon], {coupon.offer_id: {"0073341100009"}}, bought)
    text = format_clip(10, 2, found, [{"coupon_id": coupon.id, "ok": True}], 0, 1.2)
    assert "clipped 1 of 1" in text
    assert "clipped 1  Save $3.00 on illy Coffee" in text
    failed = format_clip(10, 2, found, [{"coupon_id": coupon.id, "ok": False, "detail": "403"}], 0, 1.2)
    assert "FAILED 1" in failed
    assert "403" in failed
