"""
luxella_mcp.py

Luxella ka MCP server (stdio) - Claude aur Hermes dono se chalta hai.
4 tools: sync_catalog, check_availability, price_report, query.

Sab kuch default READ-ONLY / dry-run hai. Shopify pe likhne wala sirf
luxella_sync_catalog hai, aur wo bhi sirf confirm=True pe - tab ye
repo ke hi shopify_push.run() + shopify_sync.run() chalata hai (same
logic jo GitHub Actions chalata hai, alag copy nahi), taaki Supabase ka
pushed/synced state bhi sahi update ho aur double-push na ho.

Secrets ~/.luxella.env se aate hain:
    SUPABASE_URL, SUPABASE_SERVICE_KEY
    SHOPIFY_TOKEN  (ya SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET)
    SHOPIFY_STORE_DOMAIN (default luxella-9299.myshopify.com)

Run:  .venv/bin/python luxella_mcp.py
"""
import functools
import io
import os
from contextlib import redirect_stdout
from typing import Literal

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from supabase import create_client

import shopify_push
import shopify_sync
from dedup_utils import compute_fingerprint

load_dotenv(os.path.expanduser("~/.luxella.env"))
os.environ.setdefault("SHOPIFY_STORE_DOMAIN", "luxella-9299.myshopify.com")

# Static token mile to pipeline ka client-credentials grant skip karo
if os.environ.get("SHOPIFY_TOKEN"):
    shopify_push.get_access_token = shopify_sync.get_access_token = lambda: os.environ["SHOPIFY_TOKEN"]

MAX_LIMIT = 200
SAMPLE_SIZE = 20  # response mein kitne example rows dikhane hain (context chhota rakhne ke liye)

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)

mcp = MCPServer("luxella_mcp")
_sb = None


def sb():
    global _sb
    if _sb is None:
        if not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY")):
            raise ValueError("SUPABASE_URL / SUPABASE_SERVICE_KEY missing - add them to ~/.luxella.env")
        _sb = create_client(os.environ["SUPABASE_URL"].strip(), os.environ["SUPABASE_SERVICE_KEY"].strip())
    return _sb


def surface_errors(fn):
    """MCP v2 plain exceptions ka message chhupa deta hai - ToolError mein
    wrap karo taaki agent ko asli wajah dikhe (missing key, galat column...)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"{type(e).__name__}: {e}") from e
    return wrapper


def _clamp(limit):
    return max(1, min(limit, MAX_LIMIT))


def price_stock_changes(p):
    """Wahi check jo shopify_sync.run() karta hai - kya is product ka
    price/MRP/stock Shopify pe update hoga. None = variant IDs missing
    (sync isko skip karta hai)."""
    # ponytail: shopify_sync.run() ki inline logic ki copy - wahan badle to yahan bhi badlo
    if not p.get("shopify_variant_id") or not p.get("shopify_inventory_item_id"):
        return None
    price, last_price = p.get("selling_price_inr"), p.get("last_synced_price_inr")
    mrp, last_mrp = p.get("compare_at_price_inr"), p.get("last_synced_compare_at_price_inr")
    stock, last_stock = bool(p.get("in_stock")), p.get("last_synced_in_stock")
    changes = []
    if price is not None and (last_price is None or float(price) != float(last_price)):
        changes.append(f"price {last_price} -> {price}")
    if mrp is not None and (last_mrp is None or float(mrp) != float(last_mrp)):
        changes.append(f"compare_at {last_mrp} -> {mrp}")
    if last_stock is None or stock != last_stock:
        changes.append(f"in_stock {last_stock} -> {stock}")
    return changes


def is_duplicate(fp_prices, fingerprint, price):
    """shopify_push.run() ka duplicate rule: cheaper/equal version pehle se pushed hai."""
    existing = fp_prices.get(fingerprint)
    return existing is not None and price is not None and existing <= price


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
@surface_errors
def luxella_sync_catalog(limit: int = 50, confirm: bool = False) -> dict:
    """Preview (default) or run one Supabase -> Shopify sync batch.

    Looks at the next `limit` unpushed products (would be created on Shopify,
    minus duplicates) and the `limit` oldest-synced pushed products (price /
    compare-at / stock updates). Dry-run by default: nothing is written.
    Set confirm=True to actually run shopify_push + shopify_sync for that batch
    (writes to Shopify and marks rows synced in Supabase).
    """
    limit = _clamp(limit)

    if confirm:
        shopify_push.BATCH_SIZE = shopify_sync.BATCH_SIZE = limit
        log = io.StringIO()
        # stdout = MCP protocol channel, pipeline ke print() usme nahi jaane chahiye
        with redirect_stdout(log):
            pushed = shopify_push.run()
            updated = shopify_sync.run()
        return {"mode": "applied", "created": pushed, "updated": updated,
                "log_tail": log.getvalue().splitlines()[-40:]}

    client = sb()
    pending = shopify_push.fetch_pending_products(client, limit)
    fp_prices = shopify_push.get_existing_fingerprint_prices(client) if pending else {}
    to_create, dupes = [], []
    for p in pending:
        row = {"id": p["id"], "brand": p.get("brand"), "name": p.get("name"),
               "selling_price_inr": p.get("selling_price_inr"), "in_stock": p.get("in_stock")}
        fp = compute_fingerprint(p.get("brand"), p.get("name"))
        (dupes if is_duplicate(fp_prices, fp, p.get("selling_price_inr")) else to_create).append(row)

    to_update, skipped = [], 0
    for p in shopify_sync.fetch_synced_products(client, limit):
        changes = price_stock_changes(p)
        if changes is None:
            skipped += 1
        elif changes:
            to_update.append({"id": p["id"], "name": p.get("name"), "changes": changes})

    return {
        "mode": "dry_run",
        "would_create": len(to_create),
        "would_skip_duplicate": len(dupes),
        "would_update": len(to_update),
        "skipped_missing_variant_ids": skipped,
        "create_sample": to_create[:SAMPLE_SIZE],
        "update_sample": to_update[:SAMPLE_SIZE],
        "next_step": "Re-run with confirm=True to apply this batch." if (to_create or to_update) else "Nothing to do.",
    }


@mcp.tool(annotations=READ_ONLY)
@surface_errors
def luxella_check_availability(limit: int = 50, offset: int = 0) -> dict:
    """List products that went out of stock at the source retailer but are
    still in stock on the Luxella Shopify store (last synced as in stock).
    These are the ones customers can still order but you can't buy."""
    resp = (
        sb().table("products")
        .select("id,name,brand,site,product_url,shopify_product_id,last_checked_at,shopify_synced_at", count="exact")
        .eq("pushed_to_shopify", True)
        .eq("in_stock", False)
        .eq("last_synced_in_stock", True)
        .order("last_checked_at", desc=True)
        .range(offset, offset + _clamp(limit) - 1)
        .execute()
    )
    return {"total": resp.count, "offset": offset, "items": resp.data,
            "has_more": resp.count is not None and offset + len(resp.data) < resp.count}


@mcp.tool(annotations=READ_ONLY)
@surface_errors
def luxella_price_report(brand: str | None = None, site: str | None = None, pushed_only: bool = True,
                         limit: int = 50, offset: int = 0) -> dict:
    """Source price vs landed cost vs Luxella selling price, with margin, per
    product. `store_stale` = Shopify still has an older price than Supabase.
    Filter by brand (case-insensitive substring) or exact site key."""
    q = (sb().table("products")
         .select("id,name,brand,site,currency,price,landed_cost_inr,selling_price_inr,"
                 "compare_at_price_inr,last_synced_price_inr,in_stock", count="exact")
         .not_.is_("selling_price_inr", "null"))
    if pushed_only:
        q = q.eq("pushed_to_shopify", True)
    if brand:
        q = q.ilike("brand", f"%{brand}%")
    if site:
        q = q.eq("site", site)
    resp = q.order("id").range(offset, offset + _clamp(limit) - 1).execute()

    items = []
    for r in resp.data:
        sell, landed, synced = r.get("selling_price_inr"), r.get("landed_cost_inr"), r.get("last_synced_price_inr")
        margin = round(float(sell) - float(landed), 2) if sell is not None and landed else None
        items.append({**r,
                      "margin_inr": margin,
                      "margin_pct": round(margin / float(landed) * 100, 1) if margin is not None else None,
                      "store_stale": synced is not None and float(synced) != float(sell)})
    return {"total": resp.count, "offset": offset, "items": items,
            "has_more": resp.count is not None and offset + len(items) < resp.count}


@mcp.tool(annotations=READ_ONLY)
@surface_errors
def luxella_query(table: Literal["products", "product_changes"], columns: str = "*",
                  eq: dict[str, str | int | float | bool] | None = None,
                  ilike: dict[str, str] | None = None,
                  order_by: str | None = None, desc: bool = True,
                  limit: int = 50, offset: int = 0) -> dict:
    """Read-only lookup on the Luxella Supabase tables.
    eq: exact matches, e.g. {"site": "coach", "in_stock": true}.
    ilike: case-insensitive patterns, e.g. {"name": "%tabby%"}.
    product_changes has the price/stock change log (change_type, old_value, new_value)."""
    q = sb().table(table).select(columns, count="exact")
    for col, val in (eq or {}).items():
        q = q.eq(col, val)
    for col, pat in (ilike or {}).items():
        q = q.ilike(col, pat)
    if order_by:
        q = q.order(order_by, desc=desc)
    resp = q.range(offset, offset + _clamp(limit) - 1).execute()
    return {"total": resp.count, "offset": offset, "items": resp.data,
            "has_more": resp.count is not None and offset + len(resp.data) < resp.count}


if __name__ == "__main__":
    mcp.run()
