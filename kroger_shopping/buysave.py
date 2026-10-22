"""Match purchase history to the current Buy and Save event. Does not clip or add to cart."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, urlparse

from .clipcoupon import Purchase, load_purchases
from .purchase_history import CdpError, _cdp_json, _evaluate
from .receipts import DEFAULT_RECEIPTS_DIR

SEARCH_URL = "https://www.kroger.com/atlas/v1/search/v1/products-search"
PRODUCTS_URL = "https://www.kroger.com/atlas/v1/product/v2/products"
PAGE_MARK = "kroger.com/pr/buy-and-save"


@dataclass(frozen=True)
class Event:
    offer_code: str
    description: str
    end: str


def shop_all_keyword(href: str) -> str | None:
    """Return the Shop All marketing keyword, not a sponsored search link."""
    parsed = urlparse(href or "")
    query = parse_qs(parsed.query)
    if (query.get("monet") or [""])[0] != "curated":
        return None
    keyword = (query.get("keyword") or [""])[0].strip()
    return keyword or None


def pick_event(products: Sequence[Mapping[str, Any]]) -> Event | None:
    """Take the mega-event offer from the first Shop All product that has one."""
    for product in products:
        for offer in product.get("offers") or []:
            if offer.get("displayTemplate") != "MEGA_EVENT":
                continue
            code = str(offer.get("offerCode") or "").strip()
            if not code:
                continue
            return Event(
                code,
                str(offer.get("defaultDescription") or "").strip(),
                str(offer.get("end") or ""),
            )
    return None


def format_report(
    event: Event,
    purchases: Sequence[Purchase],
    hits: Sequence[Mapping[str, Any]],
    failures: int,
) -> str:
    by_upc = {item.upc: item for item in purchases}
    rows = []
    for hit in hits:
        upc = str(hit.get("upc") or "")
        item = by_upc.get(upc)
        if item is None:
            continue
        rows.append((item.count, item.last_date, upc, item.name or str(hit.get("description") or "")))
    rows.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    lines = [
        f"{event.description}  exp {event.end[:10]}",
        f"history {len(purchases)}  matched {len(rows)}  lookup failures {failures}",
    ]
    if not rows:
        lines.extend(["", "No purchased items are in this event."])
        return "\n".join(lines)
    lines.append("")
    for count, last, upc, name in rows:
        lines.append(f"{count}  {last}  {upc}  {name}")
    return "\n".join(lines)


def report(receipts_dir=DEFAULT_RECEIPTS_DIR) -> str:
    """Read the open Buy and Save tab and report purchased items in this week's event."""
    purchases = load_purchases(receipts_dir)
    if not purchases:
        return "No local purchase history found."
    ws_url = _page_ws_url()
    discovered = _evaluate(ws_url, _discover_expression(), 60)
    parsed = json.loads(discovered)
    if parsed.get("error"):
        raise CdpError(str(parsed["error"]))
    event = pick_event(parsed.get("products") or [])
    if event is None:
        raise CdpError("Could not read the Buy and Save event from the Shop All products.")
    payload = _evaluate(ws_url, _lookup_expression(event.offer_code, [item.upc for item in purchases]), 180)
    looked = json.loads(payload)
    if looked.get("error"):
        raise CdpError(str(looked["error"]))
    return format_report(event, purchases, looked.get("hits") or [], int(looked.get("failures") or 0))


def _page_ws_url() -> str:
    version = _cdp_json("127.0.0.1", 9222, "/json/version")
    if not isinstance(version, dict) or not version.get("webSocketDebuggerUrl"):
        raise CdpError("Chrome DevTools is not answering on this port.")
    targets = _cdp_json("127.0.0.1", 9222, "/json/list")
    if not isinstance(targets, list):
        raise CdpError("Chrome DevTools target list is unreadable.")
    page = next(
        (
            target for target in targets
            if target.get("type") == "page" and PAGE_MARK in str(target.get("url") or "")
        ),
        None,
    )
    if page is None or not page.get("webSocketDebuggerUrl"):
        raise CdpError(
            "No kroger.com/pr/buy-and-save tab. Open Buy and Save in the CDP browser while logged in."
        )
    return str(page["webSocketDebuggerUrl"])


def _discover_expression() -> str:
    search = json.dumps(SEARCH_URL)
    products = json.dumps(PRODUCTS_URL)
    return f"""(async () => {{
  const link = [...document.querySelectorAll('a')].find(a => {{
    const text = (a.innerText || '').trim();
    return text === 'Shop All' && a.href.includes('keyword=') && a.href.includes('monet=curated');
  }});
  if (!link) return JSON.stringify({{error: "Could not find the Shop All link on the Buy and Save page."}});
  const el = document.querySelector('[data-testid="KrogerHeader-SearchV2"]') || document.body;
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
  const row = Array.isArray(laf) ? laf[0] : laf;
  const sources = row && row.sources;
  const source = Array.isArray(sources) ? sources[0] : sources;
  const storeId = source && source.storeId;
  if (!storeId) return JSON.stringify({{error: "Could not read the store id for this event."}});
  function headers() {{
    const h = {{"accept":"application/json","x-kroger-channel":"WEB","x-laf-object": JSON.stringify(laf)}};
    if (window.bmak && window.bmak.get_telemetry) h["Akamai-BM-Telemetry"] = bmak.get_telemetry();
    return h;
  }}
  const params = new URLSearchParams();
  params.set("option.personalization", "RELEVANCE");
  params.set("option.monetization", "CURATED");
  params.set("page.size", "8");
  params.set("page.offset", "0");
  params.set("projections", "products.compact");
  params.set("filter.locationId", storeId);
  params.set("filter.keyword", new URL(link.href).searchParams.get("keyword"));
  for (const method of ["PICKUP", "DELIVERY", "IN_STORE"]) params.append("filter.fulfillmentMethods", method);
  const search = await fetch({search} + "?" + params.toString(), {{credentials:"include", headers: headers()}});
  const searched = await search.json();
  if (!search.ok) return JSON.stringify({{error: "Shop All search failed."}});
  const gtins = ((searched.data && searched.data.productsSearch) || []).map(row => row.gtin13 || row.upc).filter(Boolean).slice(0, 8);
  if (!gtins.length) return JSON.stringify({{error: "Shop All search returned no products."}});
  const productParams = new URLSearchParams();
  for (const upc of gtins) productParams.append("filter.gtin13s", upc);
  productParams.set("filter.verified", "true");
  productParams.set("projections", "items.compact,offers.compact");
  const res = await fetch({products} + "?" + productParams.toString(), {{credentials:"include", headers: headers()}});
  const parsed = await res.json();
  if (!res.ok) return JSON.stringify({{error: "Shop All product lookup failed."}});
  const products = ((parsed.data && parsed.data.products) || []).map(product => ({{
    offers: (product.offers || []).map(offer => ({{
      offerCode: offer.offerCode,
      displayTemplate: offer.displayTemplate,
      defaultDescription: offer.defaultDescription,
      end: offer.end
    }}))
  }}));
  return JSON.stringify({{href: link.href, products}});
}})()"""


def _lookup_expression(offer_code: str, upcs: Sequence[str]) -> str:
    encoded = json.dumps(list(upcs))
    code = json.dumps(offer_code)
    products = json.dumps(PRODUCTS_URL)
    return f"""(async () => {{
  const upcs = {encoded};
  const offerCode = {code};
  const el = document.querySelector('[data-testid="KrogerHeader-SearchV2"]') || document.body;
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
  const hits = [];
  let failures = 0;
  for (let i = 0; i < upcs.length; i += 40) {{
    const batch = upcs.slice(i, i + 40);
    const params = new URLSearchParams();
    for (const upc of batch) params.append("filter.gtin13s", upc);
    params.set("filter.verified", "true");
    params.set("projections", "items.compact,offers.compact");
    const res = await fetch({products} + "?" + params.toString(), {{credentials:"include", headers: headers()}});
    if (!res.ok) {{ failures += 1; continue; }}
    const parsed = await res.json();
    for (const product of (parsed.data && parsed.data.products) || []) {{
      const offer = (product.offers || []).find(item => item.offerCode === offerCode);
      if (!offer) continue;
      const item = product.item || {{}};
      hits.push({{upc: offer.gtin13 || item.gtin13, description: item.description || ""}});
    }}
    await new Promise(r => setTimeout(r, 150));
  }}
  return JSON.stringify({{hits, failures}});
}})()"""
