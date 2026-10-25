#!/usr/bin/env node
/**
 * Pull Kroger purchase history from the already-logged-in CDP Chrome
 * and write purchase-history.json for the kroger-shopping receipt loader.
 *
 * Prerequisites:
 *   - Chrome with remote debugging on 127.0.0.1:9222
 *   - A tab on https://www.kroger.com/mypurchases (user already signed in)
 *
 * Usage:
 *   node scripts/download_receipts_cdp.mjs
 *
 * Does not type credentials or export cookies. Overwrites purchase-history.json
 * only. Leaves official Kroger PDF receipts alone.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PORT = process.env.CDP_PORT || "9222";
const HOST = process.env.CDP_HOST || "127.0.0.1";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR =
  process.env.KROGER_RECEIPTS_DIR ||
  path.resolve(__dirname, "..", "receipts");
const OUT_FILE = path.join(OUT_DIR, "purchase-history.json");
const PAGE_SIZE = 10;
const SEARCH =
  "https://www.kroger.com/atlas/v1/post-order/v1/purchase-history-search";

function uniqueUpcs(order) {
  const seen = new Set();
  const upcs = [];
  for (const item of order.lineItems || []) {
    const u = String(item.upc || "");
    if (/^\d{13}$/.test(u) && !seen.has(u)) {
      seen.add(u);
      upcs.push(u);
    }
  }
  return upcs;
}

function normalize(order) {
  const created = order.createdDateTime?.value || "";
  return {
    receiptKey: order.receiptKey,
    orderDate: created.slice(0, 10) || null,
    createdDateTime: created || null,
    purchaseType: order.purchaseType || null,
    total: order.total || null,
    status: order.status || null,
    handoffStoreId: order.handoffStoreId || null,
    fulfillmentPartner: order.fulfillmentPartner || null,
    upcs: uniqueUpcs(order),
  };
}

async function cdpJson(pathname) {
  const r = await fetch(`http://${HOST}:${PORT}${pathname}`);
  if (!r.ok) throw new Error(`${pathname} HTTP ${r.status}`);
  return r.json();
}

function cdpCall(ws, id, method, params) {
  return new Promise((resolve, reject) => {
    const onmsg = (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.id !== id) return;
      ws.removeEventListener("message", onmsg);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
      else resolve(msg.result);
    };
    ws.addEventListener("message", onmsg);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(ws, expression) {
  const result = await cdpCall(ws, 1, "Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description || "eval failed");
  }
  return result.result.value;
}

async function fetchOrders(ws) {
  const expr = `(async () => {
    const search = ${JSON.stringify(SEARCH)};
    const first = await (await fetch(search + '?pageNo=1&pageSize=${PAGE_SIZE}', {credentials:'include'})).json();
    const root = first?.data?.postOrderSearch;
    if (!root) return JSON.stringify({error: first});
    const total = root.pageTotal || 1;
    const all = (root.data || []).slice();
    for (let p = 2; p <= total; p++) {
      const j = await (await fetch(search + '?pageNo=' + p + '&pageSize=${PAGE_SIZE}', {credentials:'include'})).json();
      all.push(...(j?.data?.postOrderSearch?.data || []));
    }
    return JSON.stringify({pageTotal: total, count: all.length, orders: all});
  })()`;
  const raw = await evaluate(ws, expr);
  const parsed = JSON.parse(raw);
  if (parsed.error) {
    throw new Error("purchase-history-search failed: " + JSON.stringify(parsed.error).slice(0, 400));
  }
  return parsed;
}

async function main() {
  const version = await cdpJson("/json/version");
  if (!version.webSocketDebuggerUrl) {
    throw new Error("CDP /json/version has no webSocketDebuggerUrl");
  }
  const targets = await cdpJson("/json/list");
  const page = targets.find(
    (t) => t.type === "page" && /kroger\.com\/mypurchases/.test(t.url || ""),
  );
  if (!page) {
    throw new Error(
      "No kroger.com/mypurchases tab. Open purchase history in the CDP browser while logged in.",
    );
  }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve);
    ws.addEventListener("error", () => reject(new Error("CDP websocket failed")));
  });
  try {
    const { pageTotal, count, orders } = await fetchOrders(ws);
    const payload = {
      source: "kroger-atlas-purchase-history-search",
      fetchedAt: new Date().toISOString(),
      pageTotal,
      orders: orders.map(normalize),
    };
    fs.mkdirSync(OUT_DIR, { recursive: true });
    fs.writeFileSync(OUT_FILE, JSON.stringify(payload, null, 2) + "\n");
    console.log(JSON.stringify({ tab: page.url, pageTotal, orders: count, outFile: OUT_FILE }, null, 2));
  } finally {
    ws.close();
  }
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
