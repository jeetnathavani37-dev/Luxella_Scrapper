"""luxella_mcp.py ka offline self-check - bina Supabase/Shopify keys ke chalta hai.
Run: .venv/bin/python test_luxella_mcp.py"""
import asyncio
import os

for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY"):
    os.environ[k] = ""  # empty = load_dotenv ~/.luxella.env se override nahi karega

import luxella_mcp as m

base = {"shopify_variant_id": "1", "shopify_inventory_item_id": "2",
        "selling_price_inr": 9999, "last_synced_price_inr": 9999.0,
        "compare_at_price_inr": 15399, "last_synced_compare_at_price_inr": 15399,
        "in_stock": True, "last_synced_in_stock": True}

# price/stock diff (mirror of shopify_sync.run)
assert m.price_stock_changes(base) == []
assert m.price_stock_changes({**base, "selling_price_inr": 8999}) == ["price 9999.0 -> 8999"]
assert m.price_stock_changes({**base, "in_stock": False}) == ["in_stock True -> False"]
assert m.price_stock_changes({**base, "last_synced_in_stock": None}) == ["in_stock None -> True"]
assert m.price_stock_changes({**base, "shopify_variant_id": None}) is None

# duplicate rule (mirror of shopify_push.run)
assert m.is_duplicate({"fp": 5000}, "fp", 5000)
assert m.is_duplicate({"fp": 4000}, "fp", 5000)
assert not m.is_duplicate({"fp": 6000}, "fp", 5000)
assert not m.is_duplicate({}, "fp", 5000)
assert not m.is_duplicate({None: 1}, None, None)

# exactly 4 tools, only sync can write, and it defaults to dry-run
tools = {t.name: t for t in asyncio.run(m.mcp.list_tools())}
assert set(tools) == {"luxella_sync_catalog", "luxella_check_availability", "luxella_price_report", "luxella_query"}, tools
assert tools["luxella_sync_catalog"].input_schema["properties"]["confirm"]["default"] is False
assert all(tools[n].annotations.read_only_hint for n in tools if n != "luxella_sync_catalog")

# missing keys -> actionable error, not a crash
try:
    m.sb()
    raise AssertionError("expected ValueError")
except ValueError as e:
    assert "~/.luxella.env" in str(e)

# shopify_sync.fetch_synced_products: stock-mismatch rows pehle, phir rotation (no dupes)
class FakeQ:
    def __init__(self, rows): self.rows, self.n = rows, None
    def select(self, *_): return self
    def eq(self, col, val): return FakeQ([r for r in self.rows if r.get(col) == val])
    def order(self, *_a, **_k): return FakeQ(sorted(self.rows, key=lambda r: r["synced"]))
    def limit(self, n): self.n = n; return self
    def execute(self): return type("R", (), {"data": self.rows[:self.n]})()
class FakeSB:
    def __init__(self, rows): self.rows = rows
    def table(self, _): return FakeQ(self.rows)
rows = [{"id": i, "pushed_to_shopify": True, "in_stock": True, "last_synced_in_stock": True, "synced": i} for i in range(10)]
rows[7].update(in_stock=False)                       # sold out, Shopify says in stock
rows[9].update(in_stock=True, last_synced_in_stock=False)  # back in stock
got = [p["id"] for p in m.shopify_sync.fetch_synced_products(FakeSB(rows), 4)]
assert got == [7, 9, 0, 1], got
assert [p["id"] for p in m.shopify_sync.fetch_synced_products(FakeSB(rows), 1)] == [7]

print("ok")
