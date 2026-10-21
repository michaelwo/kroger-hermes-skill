"""Coupon sweep: title gate, then UPC intersection. Clip uses the page's clip-unclip call."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .purchase_history import CdpError, _cdp_json, _evaluate
from .receipts import DEFAULT_RECEIPTS_DIR, load_receipt_history

COUPONS_URL = "https://www.kroger.com/atlas/v1/savings-coupons/v2/coupons"
PRODUCTS_URL = "https://www.kroger.com/atlas/v1/savings-coupons/v1/products"
CLIP_URL = "https://www.kroger.com/atlas/v1/savings-coupons/v1/clip-unclip"

_WORD = re.compile(r"[a-z0-9]{4,}")
_PRICE = re.compile(r"^\s*\$?\d")
_NON_PRODUCT = re.compile(r"\d+\s*x points|gift card", re.I)

# Tokens that match too many unrelated coupons. A brand or a real product noun must remain.
_GENERIC = frozenset({
    "candy", "snack", "snacks", "bars", "hair", "item", "items", "brand",
    "products", "product", "original", "classic", "premium", "natural",
    "organic", "fresh", "whole", "sliced", "ground", "style", "size",
    "variety", "count", "pack", "family", "value", "daily", "total",
    "plus", "mini", "super", "light", "dark", "mild", "extra", "large",
    "medium", "small", "white", "yellow", "green", "free", "pure", "real",
    "foods", "selection", "simple", "truth", "kroger", "private",
})


@dataclass(frozen=True)
class Purchase:
    upc: str
    name: str
    count: int
    last_date: str


@dataclass(frozen=True)
class Coupon:
    id: str
    offer_id: str
    brand: str
    short: str
    requirement: str
    expiration: str
    savings: Any
    added: bool
    requirement_ids: tuple[str, ...]
    coupon_type: str


@dataclass(frozen=True)
class ClipHit:
    coupon: Coupon
    purchases: tuple[Purchase, ...]

    @property
    def price_deal(self) -> bool:
        return bool(_PRICE.match(self.coupon.short or ""))


def tokens(text: str) -> set[str]:
    return {word for word in _WORD.findall((text or "").lower()) if word not in _GENERIC}


def is_candidate(coupon: Coupon, purchases: Iterable[Purchase]) -> bool:
    """True when coupon copy shares a distinctive token with a purchased title."""
    if coupon.added or _NON_PRODUCT.search(coupon.short or ""):
        return False
    purchased = set()
    for item in purchases:
        purchased |= tokens(item.name)
    if not purchased:
        return False
    blob = " ".join((coupon.brand, coupon.short, coupon.requirement))
    return bool(tokens(blob) & purchased)


def hits_for(
    coupons: Iterable[Coupon],
    qualifying: dict[str, set[str]],
    purchases: Iterable[Purchase],
) -> list[ClipHit]:
    by_upc: dict[str, Purchase] = {}
    for item in purchases:
        current = by_upc.get(item.upc)
        if current is None or item.last_date >= current.last_date:
            by_upc[item.upc] = item
    found = []
    for coupon in coupons:
        if not is_candidate(coupon, by_upc.values()):
            continue
        matched = qualifying.get(coupon.offer_id) or set()
        rows = tuple(
            by_upc[upc] for upc in sorted(matched)
            if upc in by_upc and by_upc[upc].name
        )
        if rows:
            found.append(ClipHit(coupon, rows))
    return found


def format_dry_run(
    catalog_count: int,
    candidate_count: int,
    hits: list[ClipHit],
    lookup_failures: int,
    elapsed_seconds: float,
) -> str:
    lines = [
        f"Dry run. Catalog {catalog_count}. Title candidates {candidate_count}. "
        f"Would clip {len(hits)}. Lookup failures {lookup_failures}. "
        f"{elapsed_seconds:.1f}s. Nothing was clipped.",
    ]
    if not hits:
        return "\n".join(lines)
    for hit in hits:
        coupon = hit.coupon
        price = " PRICE" if hit.price_deal else ""
        exp = (coupon.expiration or "")[:10]
        lines.append(f"would clip {coupon.id}  {coupon.short}{price}  exp {exp}")
        for item in hit.purchases:
            lines.append(
                f"  {item.upc}  {item.name}  {item.count}  last {item.last_date}"
            )
    return "\n".join(lines)


def load_purchases(receipts_dir=DEFAULT_RECEIPTS_DIR) -> list[Purchase]:
    counts: dict[str, int] = defaultdict(int)
    last: dict[str, str] = {}
    names: dict[str, str] = {}
    for receipt in load_receipt_history(receipts_dir):
        if not receipt.readable:
            continue
        date = receipt.order_date or ""
        named = dict(receipt.product_names)
        for upc in receipt.upcs:
            counts[upc] += 1
            if date and date >= last.get(upc, ""):
                last[upc] = date
                if named.get(upc):
                    names[upc] = named[upc]
            elif upc not in names and named.get(upc):
                names[upc] = named[upc]
    return [
        Purchase(upc, names.get(upc, ""), counts[upc], last.get(upc, ""))
        for upc in sorted(counts)
    ]


def format_clip(
    catalog_count: int,
    candidate_count: int,
    hits: Sequence[ClipHit],
    results: Sequence[Mapping[str, Any]],
    failures: int,
    elapsed: float,
) -> str:
    by_id = {str(row.get("coupon_id")): row for row in results}
    lines = [
        f"clipped {sum(1 for row in results if row.get('ok'))} of {len(hits)}",
        f"catalog {catalog_count}",
        f"title candidates {candidate_count}",
        f"upc lookup failures {failures}",
        f"elapsed {elapsed:.1f}s",
    ]
    for hit in hits:
        row = by_id.get(hit.coupon.id, {})
        state = "clipped" if row.get("ok") else "FAILED"
        price = "  PRICE" if hit.price_deal else ""
        lines.append("")
        lines.append(
            f"{state} {hit.coupon.id}  {hit.coupon.short}{price}  exp {(hit.coupon.expiration or '')[:10]}"
        )
        if not row.get("ok"):
            lines.append(f"  {row.get('detail') or 'clip failed'}")
        for purchase in hit.purchases:
            lines.append(
                f"  {purchase.upc}  {purchase.name}  {purchase.count}  last {purchase.last_date}"
            )
    if not hits:
        lines.extend(["", "Nothing matched. Nothing was clipped."])
    return "\n".join(lines)


def dry_run() -> str:
    """Run the sweep against the signed-in coupons tab. Does not clip."""
    import time

    started = time.monotonic()
    purchases = load_purchases()
    if not purchases:
        return "No local purchase history found."
    ws_url = _coupons_ws_url()
    catalog = _fetch_catalog(ws_url)
    candidates = [coupon for coupon in catalog if is_candidate(coupon, purchases)]
    qualifying, failures = _fetch_qualifying(ws_url, candidates)
    found = hits_for(candidates, qualifying, purchases)
    return format_dry_run(
        len(catalog),
        len(candidates),
        found,
        failures,
        time.monotonic() - started,
    )


def clip() -> str:
    """Clip every dry-run hit through the page's clip-unclip call."""
    import time

    started = time.monotonic()
    purchases = load_purchases()
    if not purchases:
        return "No local purchase history found."
    ws_url = _coupons_ws_url()
    catalog = _fetch_catalog(ws_url)
    candidates = [coupon for coupon in catalog if is_candidate(coupon, purchases)]
    qualifying, failures = _fetch_qualifying(ws_url, candidates)
    found = hits_for(candidates, qualifying, purchases)
    results = _clip(ws_url, found) if found else []
    return format_clip(
        len(catalog),
        len(candidates),
        found,
        results,
        failures,
        time.monotonic() - started,
    )


def _clip(ws_url: str, hits: Sequence[ClipHit]) -> list[dict[str, Any]]:
    payload = _evaluate(ws_url, _clip_expression([
        {"coupon_id": hit.coupon.id} for hit in hits
    ]), 120)
    parsed = json.loads(payload)
    if parsed.get("error"):
        raise CdpError(str(parsed["error"]))
    rows = parsed.get("results")
    if not isinstance(rows, list):
        raise CdpError("Clip response was not a list.")
    return rows


def _clip_expression(jobs: list[dict[str, str]]) -> str:
    encoded = json.dumps(jobs)
    url = json.dumps(CLIP_URL)
    return f"""(async () => {{
  const jobs = {encoded};
  const url = {url};
  const el = document.querySelector('[data-testid^="CouponCard-"]') || document.body;
  const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
  let fiber = el[fiberKey];
  let store = null;
  while (fiber && !store) {{
    const props = fiber.memoizedProps || {{}};
    if (props.store && props.store.getState) store = props.store;
    fiber = fiber.return;
  }}
  if (!store) return JSON.stringify({{error: "no store"}});
  const laf = store.getState().calypso.domains.modalityPreferences.lafObject;
  function headers() {{
    const h = {{"accept":"application/json","content-type":"application/json","x-kroger-channel":"WEB","x-laf-object": JSON.stringify(laf)}};
    if (window.bmak && window.bmak.get_telemetry) h["Akamai-BM-Telemetry"] = bmak.get_telemetry();
    return h;
  }}
  const results = [];
  for (const job of jobs) {{
    const res = await fetch(url, {{
      method: "POST",
      credentials: "include",
      headers: headers(),
      body: JSON.stringify({{action: "CLIP", couponId: String(job.coupon_id)}})
    }});
    const text = await res.text();
    const button = document.querySelector('[data-testid="CouponActionButton-' + job.coupon_id + '"]');
    const label = button ? (button.innerText || "").trim() : "";
    let detail = text.slice(0, 180);
    try {{
      const parsed = JSON.parse(text);
      if (parsed && parsed.errors) detail = JSON.stringify(parsed.errors).slice(0, 180);
    }} catch (e) {{}}
    const clipped = res.ok && !/"errors"/.test(text);
    results.push({{
      coupon_id: String(job.coupon_id),
      status: res.status,
      ok: clipped,
      button: label,
      detail: clipped ? (label || "clipped") : detail
    }});
  }}
  return JSON.stringify({{results}});
}})()"""


def _coupons_ws_url() -> str:
    version = _cdp_json("127.0.0.1", 9222, "/json/version")
    if not isinstance(version, dict) or not version.get("webSocketDebuggerUrl"):
        raise CdpError("Chrome DevTools is not answering on this port.")
    targets = _cdp_json("127.0.0.1", 9222, "/json/list")
    if not isinstance(targets, list):
        raise CdpError("Chrome DevTools target list is unreadable.")
    page = next(
        (
            target for target in targets
            if target.get("type") == "page"
            and "kroger.com/savings/cl/coupons" in str(target.get("url") or "")
        ),
        None,
    )
    if page is None or not page.get("webSocketDebuggerUrl"):
        raise CdpError(
            "No kroger.com/savings/cl/coupons tab. Open Digital Coupons in the CDP browser while logged in."
        )
    return str(page["webSocketDebuggerUrl"])


def _fetch_catalog(ws_url: str) -> list[Coupon]:
    raw = _evaluate(ws_url, _catalog_expression(), 120)
    parsed = json.loads(raw)
    if parsed.get("error"):
        raise CdpError("Kroger coupon catalog fetch failed.")
    coupons = []
    for row in parsed.get("coupons") or []:
        if not isinstance(row, dict) or not row.get("offerId") or not row.get("id"):
            continue
        coupons.append(Coupon(
            id=str(row["id"]),
            offer_id=str(row["offerId"]),
            brand=str(row.get("brand") or ""),
            short=str(row.get("short") or ""),
            requirement=str(row.get("requirement") or ""),
            expiration=str(row.get("expiration") or ""),
            savings=row.get("savings"),
            added=bool(row.get("added")),
            requirement_ids=tuple(str(item) for item in row.get("requirementIds") or []),
            coupon_type=str(row.get("type") or "standard"),
        ))
    return coupons


def _fetch_qualifying(ws_url: str, coupons: list[Coupon]) -> tuple[dict[str, set[str]], int]:
    if not coupons:
        return {}, 0
    payload = [
        {
            "offerId": coupon.offer_id,
            "type": coupon.coupon_type.lower(),
            "requirementIds": list(coupon.requirement_ids),
        }
        for coupon in coupons
    ]
    raw = _evaluate(ws_url, _qualifying_expression(payload), 300)
    parsed = json.loads(raw)
    if parsed.get("error"):
        raise CdpError("Kroger qualifying-product fetch failed.")
    qualifying = {
        offer_id: {upc for upc in upcs if isinstance(upc, str)}
        for offer_id, upcs in (parsed.get("qualifying") or {}).items()
    }
    return qualifying, int(parsed.get("failures") or 0)


def _catalog_expression() -> str:
    url = json.dumps(COUPONS_URL)
    return f"""(async () => {{
  const base = {url};
  const el = document.querySelector('[data-testid^="CouponCard-"]') || document.body;
  const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
  let fiber = el[fiberKey];
  let store = null;
  while (fiber && !store) {{
    const props = fiber.memoizedProps || {{}};
    if (props.store && props.store.getState) store = props.store;
    fiber = fiber.return;
  }}
  if (!store) return JSON.stringify({{error: "no store"}});
  const laf = store.getState().calypso.domains.modalityPreferences.lafObject;
  function headers() {{
    const h = {{"accept":"application/json","x-kroger-channel":"WEB","x-laf-object": JSON.stringify(laf)}};
    if (window.bmak && window.bmak.get_telemetry) h["Akamai-BM-Telemetry"] = bmak.get_telemetry();
    return h;
  }}
  const coupons = [];
  for (const offset of [0, 200, 400]) {{
    const res = await fetch(base + "?page.size=200&page.offset=" + offset + "&filter.onlyNewCoupons=false&filter.status=unclipped&filter.status=active", {{credentials:"include", headers: headers()}});
    const parsed = await res.json();
    if (!res.ok) return JSON.stringify({{error: parsed.errors || res.status}});
    const rows = (parsed.data && parsed.data.coupons) || [];
    for (const row of rows) {{
      coupons.push({{
        id: row.id,
        offerId: row.offerId,
        brand: row.brandName || "",
        short: row.shortDescription || row.displayDescription || "",
        requirement: row.requirementDescription || "",
        expiration: row.expirationDate || "",
        savings: row.savings,
        added: !!row.addedToCard,
        requirementIds: (row.requirements || []).map(item => item.id).filter(Boolean),
        type: row.type || "standard"
      }});
    }}
    if (rows.length < 200) break;
  }}
  return JSON.stringify({{coupons}});
}})()"""


def _qualifying_expression(payload: list[dict[str, Any]]) -> str:
    encoded = json.dumps(payload)
    url = json.dumps(PRODUCTS_URL)
    return f"""(async () => {{
  const jobs = {encoded};
  const base = {url};
  const el = document.querySelector('[data-testid^="CouponCard-"]') || document.body;
  const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
  let fiber = el[fiberKey];
  let store = null;
  while (fiber && !store) {{
    const props = fiber.memoizedProps || {{}};
    if (props.store && props.store.getState) store = props.store;
    fiber = fiber.return;
  }}
  if (!store) return JSON.stringify({{error: "no store"}});
  const laf = store.getState().calypso.domains.modalityPreferences.lafObject;
  function headers() {{
    const h = {{"accept":"application/json","x-kroger-channel":"WEB","x-laf-object": JSON.stringify(laf)}};
    if (window.bmak && window.bmak.get_telemetry) h["Akamai-BM-Telemetry"] = bmak.get_telemetry();
    return h;
  }}
  const qualifying = {{}};
  let failures = 0;
  for (const job of jobs) {{
    const params = new URLSearchParams();
    params.set("projections", "coupons.full");
    params.set("filter.type", job.type || "standard");
    for (const id of job.requirementIds || []) params.append("filter.requirementIds", id);
    try {{
      const res = await fetch(base + "/" + job.offerId + "?" + params.toString(), {{credentials:"include", headers: headers()}});
      const parsed = await res.json();
      if (!res.ok) {{ failures += 1; continue; }}
      const upcs = (parsed.data && parsed.data.coupons && parsed.data.coupons.upcs) || [];
      qualifying[job.offerId] = upcs;
    }} catch (e) {{
      failures += 1;
    }}
    await new Promise(r => setTimeout(r, 100));
  }}
  return JSON.stringify({{qualifying, failures}});
}})()"""
