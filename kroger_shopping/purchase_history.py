"""Export Kroger purchase history from a logged-in CDP Chrome tab."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .exceptions import KrogerError
from .receipts import DEFAULT_RECEIPTS_DIR, PURCHASE_HISTORY_FILENAME

SEARCH_URL = "https://www.kroger.com/atlas/v1/post-order/v1/purchase-history-search"
DETAIL_URL = "https://www.kroger.com/atlas/v1/purchase-history/v2/details"
PAGE_SIZE = 10
DETAIL_BATCH = 8
DEFAULT_CDP_HOST = "127.0.0.1"
DEFAULT_CDP_PORT = 9222


class CdpError(KrogerError):
    """Raised when Chrome DevTools Protocol is missing or the tab is unusable."""


def pull_purchase_history(
    receipts_dir: Path | None = None,
    host: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    """Fetch purchase history via CDP and write purchase-history.json."""
    host = host or os.environ.get("CDP_HOST", DEFAULT_CDP_HOST)
    port = int(os.environ.get("CDP_PORT", port or DEFAULT_CDP_PORT))
    directory = Path(receipts_dir) if receipts_dir is not None else DEFAULT_RECEIPTS_DIR
    version = _cdp_json(host, port, "/json/version")
    if not isinstance(version, dict) or not version.get("webSocketDebuggerUrl"):
        raise CdpError("Chrome DevTools is not answering on this port.")
    targets = _cdp_json(host, port, "/json/list")
    if not isinstance(targets, list):
        raise CdpError("Chrome DevTools target list is unreadable.")
    page = next(
        (
            target
            for target in targets
            if target.get("type") == "page"
            and "kroger.com/mypurchases" in str(target.get("url") or "")
        ),
        None,
    )
    if page is None:
        raise CdpError(
            "No kroger.com/mypurchases tab. Open Purchase History in the CDP browser while logged in."
        )
    ws_url = page.get("webSocketDebuggerUrl")
    if not ws_url:
        raise CdpError("Purchase History tab has no DevTools websocket.")
    raw = _evaluate(ws_url, _history_expression())
    parsed = json.loads(raw)
    if parsed.get("error"):
        raise CdpError("Kroger purchase-history-search failed.")
    orders = [normalize_order(order) for order in parsed.get("orders") or []]
    keys = [order["receiptKey"] for order in orders if order.get("receiptKey")]
    fetched: set[str] = set()
    if keys:
        detail_raw = _evaluate(ws_url, _detail_expression(keys), 180)
        detail_parsed = json.loads(detail_raw)
        if not detail_parsed.get("error"):
            fetched = apply_name_maps(
                orders,
                detail_parsed.get("names") or {},
                detail_parsed.get("fetched") or [],
            )
    path = directory / PURCHASE_HISTORY_FILENAME
    preserve_prior_names(orders, _read_orders(path), fetched)
    titled = sum(1 for order in orders if order.get("productNames"))
    payload = {
        "source": "kroger-atlas-purchase-history-search",
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "pageTotal": parsed.get("pageTotal"),
        "orders": orders,
    }
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {
        "path": path,
        "orders": len(orders),
        "pageTotal": parsed.get("pageTotal"),
        "titled": titled,
    }


def unique_upcs(order: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    upcs: list[str] = []
    for item in order.get("lineItems") or []:
        if not isinstance(item, dict):
            continue
        upc = str(item.get("upc") or "")
        if len(upc) == 13 and upc.isdigit() and upc not in seen:
            seen.add(upc)
            upcs.append(upc)
    return upcs


def product_names(order: dict[str, Any]) -> dict[str, str]:
    """Keep names supplied by purchase history, without catalog requests."""
    valid_upcs = set(unique_upcs(order))
    names = {}
    for item in order.get("lineItems") or []:
        if not isinstance(item, dict):
            continue
        upc = str(item.get("upc") or "")
        if upc not in valid_upcs:
            continue
        for key in ("description", "productName", "name"):
            name = item.get(key)
            if isinstance(name, str) and name.strip():
                names.setdefault(upc, " ".join(name.split()))
                break
    return names


def normalize_order(order: dict[str, Any]) -> dict[str, Any]:
    created = ""
    created_obj = order.get("createdDateTime")
    if isinstance(created_obj, dict):
        created = str(created_obj.get("value") or "")
    elif isinstance(created_obj, str):
        created = created_obj
    return {
        "receiptKey": order.get("receiptKey"),
        "orderDate": created[:10] or None,
        "createdDateTime": created or None,
        "purchaseType": order.get("purchaseType"),
        "total": order.get("total"),
        "status": order.get("status"),
        "handoffStoreId": order.get("handoffStoreId"),
        "fulfillmentPartner": order.get("fulfillmentPartner"),
        "upcs": unique_upcs(order),
        "productNames": product_names(order),
    }


def apply_name_maps(
    orders: list[dict[str, Any]],
    names: dict[str, Any],
    fetched: list[str],
) -> set[str]:
    """Keep detail titles only for UPCs already on the order. Return fetched keys."""
    fetched_keys = {key for key in fetched if isinstance(key, str)}
    for order in orders:
        key = order.get("receiptKey")
        if not isinstance(key, str):
            continue
        raw = names.get(key) if isinstance(names, dict) else None
        if not isinstance(raw, dict):
            continue
        valid = set(order.get("upcs") or [])
        kept = {
            upc: " ".join(name.split())
            for upc, name in raw.items()
            if upc in valid and isinstance(name, str) and name.strip()
        }
        if kept:
            order["productNames"] = kept
        elif key in fetched_keys:
            order.pop("productNames", None)
    return fetched_keys


def preserve_prior_names(
    orders: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    fetched: set[str],
) -> None:
    """Keep stored titles when that receipt's detail call did not return."""
    prior = {
        order.get("receiptKey"): order.get("productNames")
        for order in previous
        if isinstance(order, dict) and isinstance(order.get("productNames"), dict)
    }
    for order in orders:
        key = order.get("receiptKey")
        if order.get("productNames") or key in fetched:
            continue
        names = prior.get(key)
        if names:
            order["productNames"] = names


def _read_orders(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return []
    orders = payload.get("orders") if isinstance(payload, dict) else None
    if not isinstance(orders, list):
        return []
    return [order for order in orders if isinstance(order, dict)]


def _detail_expression(keys: list[str]) -> str:
    payload = json.dumps(keys)
    url = json.dumps(DETAIL_URL)
    return f"""(async () => {{
  const keys = {payload};
  const url = {url};
  const names = {{}};
  const fetched = [];
  const failed = [];
  function toBody(key) {{
    const parts = String(key).split("~");
    if (parts.length !== 5) return null;
    return {{
      divisionNumber: parts[0],
      storeNumber: parts[1],
      transactionDate: parts[2],
      terminalNumber: parts[3],
      transactionId: parts[4]
    }};
  }}
  function headers() {{
    const h = {{
      "accept": "application/json",
      "content-type": "application/json",
      "X-Kroger-Channel": "WEB"
    }};
    if (window.bmak && window.bmak.get_telemetry) {{
      h["Akamai-BM-Telemetry"] = bmak.get_telemetry();
    }}
    return h;
  }}
  for (let i = 0; i < keys.length; i += {DETAIL_BATCH}) {{
    const chunk = keys.slice(i, i + {DETAIL_BATCH});
    const body = chunk.map(toBody).filter(Boolean);
    try {{
      const res = await fetch(url, {{
        method: "POST",
        credentials: "include",
        headers: headers(),
        body: JSON.stringify(body)
      }});
      const parsed = await res.json();
      if (!res.ok) {{
        failed.push(chunk.length);
        continue;
      }}
      for (const detail of (parsed.data && parsed.data.purchaseHistoryDetails) || []) {{
        const id = detail.purchaseId && detail.purchaseId.receiptId;
        if (!id) continue;
        fetched.push(id);
        const map = {{}};
        for (const item of detail.items || []) {{
          const purchased = item.purchasedData || {{}};
          const upc = purchased.upc;
          const info = purchased.displayInfo || {{}};
          const desc = info.description;
          const size = info.customerFacingSize;
          if (typeof upc === "string" && upc.length === 13 && /^[0-9]+$/.test(upc) && typeof desc === "string" && desc.trim()) {{
            const sizeText = typeof size === "string" ? size.trim() : "";
            map[upc] = sizeText ? desc.trim() + ", " + sizeText : desc.trim();
          }}
        }}
        names[id] = map;
      }}
    }} catch (e) {{
      failed.push(chunk.length);
    }}
    await new Promise(r => setTimeout(r, 200));
  }}
  return JSON.stringify({{names, fetched, failed}});
}})()"""


def _history_expression() -> str:
    search = json.dumps(SEARCH_URL)
    return f"""(async () => {{
    const search = {search};
    const first = await (await fetch(search + '?pageNo=1&pageSize={PAGE_SIZE}', {{credentials:'include'}})).json();
    const root = first?.data?.postOrderSearch;
    if (!root) return JSON.stringify({{error: first}});
    const total = root.pageTotal || 1;
    const all = (root.data || []).slice();
    for (let p = 2; p <= total; p++) {{
      const j = await (await fetch(search + '?pageNo=' + p + '&pageSize={PAGE_SIZE}', {{credentials:'include'}})).json();
      all.push(...(j?.data?.postOrderSearch?.data || []));
    }}
    return JSON.stringify({{pageTotal: total, count: all.length, orders: all}});
  }})()"""


def _cdp_json(host: str, port: int, path: str) -> Any:
    url = f"http://{host}:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            body = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CdpError(
            f"Chrome DevTools is not reachable at {host}:{port}."
        ) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise CdpError("Chrome DevTools returned a non-JSON body.") from exc


def _evaluate(ws_url: str, expression: str, timeout: int = 20) -> str:
    sock = _ws_connect(ws_url, timeout)
    try:
        _ws_send(sock, json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
        }))
        while True:
            message = json.loads(_ws_recv(sock))
            if message.get("id") != 1:
                continue
            if message.get("error"):
                raise CdpError("DevTools evaluate failed.")
            result = message.get("result") or {}
            if result.get("exceptionDetails"):
                raise CdpError("Purchase history fetch failed in the browser tab.")
            value = (result.get("result") or {}).get("value")
            if not isinstance(value, str):
                raise CdpError("Purchase history response was not JSON text.")
            return value
    finally:
        sock.close()


def _ws_connect(ws_url: str, timeout: int = 20) -> _BufferedSocket:
    parsed = urlparse(ws_url)
    host = parsed.hostname or DEFAULT_CDP_HOST
    port = parsed.port or DEFAULT_CDP_PORT
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    sock = socket.create_connection((host, port), timeout=timeout)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(request.encode("ascii"))
    buffer = b""
    while b"\r\n\r\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            raise CdpError("Chrome closed the DevTools handshake.")
        buffer += chunk
    header, _, rest = buffer.partition(b"\r\n\r\n")
    status = header.split(b"\r\n", 1)[0]
    if b"101" not in status:
        sock.close()
        raise CdpError("Chrome rejected the DevTools websocket.")
    expected = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    )
    if expected not in header:
        sock.close()
        raise CdpError("Chrome DevTools websocket handshake failed.")
    return _BufferedSocket(sock, rest)


def _ws_send(sock: Any, payload: str) -> None:
    data = payload.encode("utf-8")
    mask = os.urandom(4)
    header = bytearray([0x81])
    length = len(data)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    header.extend(mask)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    sock.sendall(header + masked)


def _ws_recv(sock: Any) -> str:
    chunks: list[bytes] = []
    while True:
        first = _recvexact(sock, 2)
        opcode = first[0] & 0x0F
        masked = bool(first[1] & 0x80)
        length = first[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", _recvexact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", _recvexact(sock, 8))[0]
        mask = _recvexact(sock, 4) if masked else b""
        payload = _recvexact(sock, length)
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if opcode == 0x8:
            raise CdpError("Chrome closed the DevTools websocket.")
        if opcode == 0x1 or opcode == 0x0:
            chunks.append(payload)
            if first[0] & 0x80:
                return b"".join(chunks).decode("utf-8")
        # ignore ping/pong/binary


class _BufferedSocket:
    def __init__(self, sock: socket.socket, extra: bytes = b"") -> None:
        self.sock = sock
        self.buf = extra

    def recv(self, size: int) -> bytes:
        if self.buf:
            take, self.buf = self.buf[:size], self.buf[size:]
            return take
        return self.sock.recv(size)

    def sendall(self, data: bytes) -> None:
        self.sock.sendall(data)

    def close(self) -> None:
        self.sock.close()


def _recvexact(sock: Any, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        piece = sock.recv(size - len(chunks))
        if not piece:
            raise CdpError("Chrome closed the DevTools websocket.")
        chunks.extend(piece)
    return bytes(chunks)
