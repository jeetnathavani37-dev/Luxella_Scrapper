"""luxella_mcp.py ka offline self-check - bina Supabase/Shopify keys ke chalta hai.
Run: .venv/bin/python test_luxella_mcp.py"""
import asyncio
import os

for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY"):
    os.environ[k] = ""  # empty = load_dotenv ~/.luxella.env se override nahi karega

import luxella_mcp as m

base = {"shopify_variant_id": "1", "shopify_inventory_item_id": "2", "price": 59.99,
        "selling_price_inr": 9999, "last_synced_price_inr": 9999.0,
        "compare_at_price_inr": 15399, "last_synced_compare_at_price_inr": 15399,
        "in_stock": True, "last_synced_in_stock": True}

# price/stock diff (mirror of shopify_sync.run)
assert m.price_stock_changes(base) == []
assert m.price_stock_changes({**base, "selling_price_inr": 8999}) == ["price 9999.0 -> 8999"]
assert m.price_stock_changes({**base, "in_stock": False}) == ["in_stock True -> False"]
assert m.price_stock_changes({**base, "last_synced_in_stock": None}) == ["in_stock None -> True"]
assert m.price_stock_changes({**base, "shopify_variant_id": None}) is None
# source price 0: price nahi bhejte (floor Rs799), sirf stock 0
assert m.price_stock_changes({**base, "price": 0, "selling_price_inr": 799}) == ["in_stock True -> False"]

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

# preview_id: same batch -> same id; koi bhi change (id, price, limit) -> naya id
c, d, u = [{"id": 1}], [{"id": 2}], [{"id": 3, "changes": ["price 1 -> 2"]}]
pid = m.preview_id(50, c, d, u)
assert pid == m.preview_id(50, [{"id": 1}], [{"id": 2}], [{"id": 3, "changes": ["price 1 -> 2"]}])
assert pid != m.preview_id(50, c, d, [{"id": 3, "changes": ["price 1 -> 3"]}])
assert pid != m.preview_id(50, [{"id": 9}], d, u)
assert pid != m.preview_id(60, c, d, u)

# confirm gate: bina preview_id / galat preview_id -> ToolError, Shopify pe kuch nahi likha
m.sb = lambda: None
m.preview_batch = lambda client, limit: {"mode": "dry_run", "preview_id": "abc123"}
calls = []
m.shopify_push.run = lambda: calls.append("push") or 1
m.shopify_sync.run = lambda: calls.append("sync") or 2
for bad in (None, "stale"):
    try:
        m.luxella_sync_catalog(limit=50, confirm=True, preview_id=bad)
        raise AssertionError("expected ToolError")
    except m.ToolError:
        pass
assert calls == [], calls
assert m.luxella_sync_catalog(limit=50)["mode"] == "dry_run" and calls == []
assert m.luxella_sync_catalog(limit=50, confirm=True, preview_id="abc123")["mode"] == "applied"
assert calls == ["push", "sync"]

# partial failure: error mein log tail aata hai taaki agent ko pata ho kya likh gaya
def half_push():
    print("[PUSHED] Coach Tabby")
    raise RuntimeError("token expired")
m.shopify_push.run = half_push
try:
    m.luxella_sync_catalog(limit=50, confirm=True, preview_id="abc123")
    raise AssertionError("expected ToolError")
except m.ToolError as e:
    assert "token expired" in str(e) and "[PUSHED] Coach Tabby" in str(e), e

# luxella_query: products ka default slim, product_changes ka "*"
import inspect
assert inspect.signature(m.luxella_query).parameters["columns"].default is None
assert "description" not in m.DEFAULT_PRODUCT_COLUMNS

# MCP preview: size signature badla -> "sizes changed"; null signature (repair pending) -> kuch nahi
_mp = {**base, "category": "shoes", "currency": "USD", "name": "Sandal",
       "variants": [{"size": "6", "price": 59.99, "in_stock": True}, {"size": "7", "price": 59.99, "in_stock": True}]}
assert m.price_stock_changes({**_mp, "last_synced_variant_stock": None}) == []
_sig = m.shopify_sync.stock_signature(_mp)
assert m.price_stock_changes({**_mp, "last_synced_variant_stock": _sig}) == []
_mp7 = {**_mp, "variants": [{"size": "6", "price": 59.99, "in_stock": True}, {"size": "7", "price": 59.99, "in_stock": False}]}
assert m.price_stock_changes({**_mp7, "last_synced_variant_stock": _sig}) == ["sizes changed"]

# per-size stock (2026-10-05): har size ka target, sirf pehla variant nahi
ss = m.shopify_sync
sizes13 = [str(s) for s in (5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5, 10, 11, 12)]
shop13 = [{"inventory_item_id": f"i{s}", "size": s, "available": 10} for s in sizes13]
oos = {"price": 89.0, "in_stock": False, "category": "shoes", "currency": "USD", "name": "Sandal",
       "variants": [{"size": s, "price": 89.0, "in_stock": False} for s in sizes13]}
# product-level in_stock = sirf pehla size: pehla sold out, baaki available -> baaki 10 hi rahen (sandal galti)
first_oos = {**oos, "variants": [{"size": s, "price": 89.0, "in_stock": s != "5"} for s in sizes13]}
changes, _, _ = ss.size_targets(first_oos, shop13)
assert changes == [("i5", 10, 0)], changes
changes, skipped, unmatched = ss.size_targets(oos, shop13)
assert len(changes) == 13 and all(t == 0 for _, _, t in changes), changes
partial = {**oos, "in_stock": True,
           "variants": [{"size": s, "price": 89.0, "in_stock": s not in ("6", "7")} for s in sizes13]}
changes, _, _ = ss.size_targets(partial, shop13)
assert sorted(i for i, _, _ in changes) == ["i6", "i7"] and all(t == 0 for _, _, t in changes), changes
# 1..9 = customer order ke baad - chhoona nahi; Shopify-only size -> 0 + unmatched
shop_odd = [{"inventory_item_id": "iA", "size": "6", "available": 3},
            {"inventory_item_id": "iB", "size": "US 7", "available": 10}]
changes, skipped, unmatched = ss.size_targets(oos, shop_odd)
assert changes == [] and skipped == [("iA", "6", 3)] and unmatched == ["US 7"], (changes, skipped, unmatched)
# price 0 -> sab sizes 0; single-size product -> koi signature nahi
assert all(t == 0 for _, _, t in ss.size_targets({**partial, "price": 0}, shop13)[0])
assert ss.stock_signature({**oos, "variants": [{"size": "7", "price": 89.0, "in_stock": True}]}) is None
# signature same = koi Shopify call ki zaroorat nahi; size badla = signature badla
assert ss.stock_signature(partial) == ss.stock_signature(dict(partial))
assert ss.stock_signature(partial) != ss.stock_signature(oos)

# shopify_sync.run() multi-size raste (upar run() mock hua tha - fresh copy lo)
import importlib
ss = importlib.reload(m.shopify_sync)
calls = []
ss.get_supabase = lambda: None
ss.get_access_token = lambda: "t"
ss.time.sleep = lambda s: None
ss.update_variant = lambda *a: calls.append("variant")
ss.update_stock = lambda *a: calls.append("first_variant_stock")
ss.sync_sizes = lambda tok, p: calls.append(("sizes", p["id"])) or ([("i6", 10, 0)], [], [], True)
ss.mark_synced = lambda sb, pid, *a: calls.append(("mark", pid, a[-1] if len(a) == 4 else None))
row = {"price": 89.0, "selling_price_inr": 9999, "compare_at_price_inr": None, "in_stock": True,
       "shopify_variant_id": "v", "shopify_inventory_item_id": "i5", "shopify_product_id": "p",
       "last_synced_price_inr": 9999, "last_synced_compare_at_price_inr": None, "last_synced_in_stock": True,
       "category": "shoes", "currency": "USD", "name": "Sandal", "variants": partial["variants"]}
sig = ss.stock_signature(row)
ss.fetch_synced_products = lambda sb, n: [
    {**row, "id": 1, "last_synced_variant_stock": sig},                    # same -> koi Shopify call nahi
    {**row, "id": 2, "last_synced_variant_stock": "old"},                  # badla -> sync_sizes + naya sig
    {**row, "id": 3, "last_synced_variant_stock": None, "in_stock": False}, # repair pending -> purana raasta
]
ss.run()
assert ("sizes", 1) not in calls and ("sizes", 2) in calls, calls
assert ("mark", 1, sig) in calls and ("mark", 2, sig) in calls and ("mark", 3, None) in calls, calls
assert calls.count("first_variant_stock") == 1, calls  # sirf row 3 (null signature)

# push: naye product ke saath size signature save hota hai (sync turant per-size raste pe)
_upd = {}
class _SB:
    def table(self, _):
        class Q:
            def update(q, d): _upd.update(d); return q
            def eq(q, *a): return q
            def execute(q): return None
        return Q()
m.shopify_push.mark_pushed(_SB(), 1, {"id": 9, "variants": [{"id": 1, "inventory_item_id": 2, "price": "9999"}]},
                           True, None, "fp", sig)
assert _upd["last_synced_variant_stock"] == sig, _upd

# repair_variant_stock: plan totals, --limit sirf badalne wale, signature sirf apply pe
import repair_variant_stock as rv
rv.ss = ss
_p1 = {**row, "id": 11, "site": "s", "shopify_product_id": "P1", "variants": first_oos["variants"]}  # size 5 sold out
_p2 = {**row, "id": 12, "site": "s", "shopify_product_id": "P2", "variants": first_oos["variants"]}  # already right
_shop = {"P1": [{"inventory_item_id": f"i{s}", "size": s, "available": 10} for s in sizes13],
         "P2": [{"inventory_item_id": f"j{s}", "size": s, "available": 0 if s == "5" else 10} for s in sizes13]}
rv.shopify_sizes_bulk = lambda tok, pids: {p: _shop[p] for p in pids if p in _shop}
items, totals = rv.plan("t", [_p1, _p2, {**_p1, "id": 13, "shopify_product_id": "GONE"}])
assert totals["products_changing"] == 1 and totals["sizes_to_0"] == 1 and totals["missing_on_shopify"] == 1, totals
_writes, _sigs = [], []
ss.set_size_quantities = lambda tok, ch, ref: _writes.append(ch)
class _SB2:
    def table(self, _):
        class Q:
            def update(q, d): _sigs.append(d["last_synced_variant_stock"]); return q
            def eq(q, *a): return q
            def execute(q): return None
        return Q()
import tempfile
import json as _json
_bk = tempfile.mktemp(suffix=".jsonl")
assert rv.apply(_SB2(), "t", items, limit=5, backup_path=_bk) == (1, []) and _writes == [[("i5", 10, 0)]] and len(_sigs) == 1
assert [_json.loads(line)["inventory_item_id"] for line in open(_bk)] == ["i5"]  # backup = sirf applied
_writes.clear(); _sigs.clear()
rv.apply(_SB2(), "t", items, limit=0, backup_path=_bk)  # full run: dono ko signature, P2 pe koi Shopify write nahi
assert len(_writes) == 1 and len(_sigs) == 2, (_writes, _sigs)
# CAS stale (beech mein order): product chhodo, signature nahi, run chalta rahe
def _stale(tok, ch, ref): raise ss.StaleQuantity("x")
ss.set_size_quantities = _stale
_sigs.clear()
assert rv.apply(_SB2(), "t", items, limit=0, backup_path=_bk) == (0, [11]) and len(_sigs) == 1  # sirf P2
assert open(_bk).read() == ""
# sync: unmatched size -> kuch mat likho, signature mat badlo; size label whitespace match
ss = importlib.reload(m.shopify_sync)
ss.time.sleep = lambda s: None
_w = []
ss.set_size_quantities = lambda tok, ch, ref: _w.append(ch)
ss.fetch_shopify_sizes = lambda tok, pid: [{"inventory_item_id": "x", "size": "US 7", "available": 10}]
assert ss.sync_sizes("t", {**_p1})[3] is False and _w == []
ss.fetch_shopify_sizes = lambda tok, pid: [{"inventory_item_id": f"i{s}", "size": f" {s} ", "available": 10} for s in sizes13]
assert ss.sync_sizes("t", {**_p1})[3] is True and _w == [[("i5", 10, 0)]], _w
assert "@idempotent(key: $idempotencyKey)" in ss.SET_QTY_MUTATION
# 13 mein se 1 size unmatched (jaise retailer ne size hata diya) -> baaki sync ho, unmatched ko chhoo nahi
_w.clear()
ss.fetch_shopify_sizes = lambda tok, pid: ([{"inventory_item_id": f"i{s}", "size": s, "available": 10} for s in sizes13]
                                           + [{"inventory_item_id": "iX", "size": "13", "available": 10}])
r = ss.sync_sizes("t", {**_p1})
assert r[3] is True and r[2] == ["13"] and _w == [[("i5", 10, 0)]], (r, _w)
# idempotency key har call nayi (same badlaav 6 ghante baad dobara bhi apply ho, Shopify skip na kare)
ss = importlib.reload(m.shopify_sync)
_keys = []
ss.shopify_graphql = lambda tok, q, v: _keys.append(v["idempotencyKey"]) or {"inventorySetQuantities": {"userErrors": []}}
ss.set_size_quantities("t", [("i6", 10, 0)], "ref")
ss.set_size_quantities("t", [("i6", 10, 0)], "ref")
assert len(_keys) == 2 and _keys[0] != _keys[1], _keys

# shopify_scraper.scrape_shopify_catalog: complete sirf jab khaali page pe pagination khatam ho
import requests as _rq
import shopify_scraper as sc
_cfg = {"domain": "https://x.com", "name": "x", "currency": "USD", "category": "bags"}
def _prod(h, title="Bag", price="10.00"):
    return {"handle": h, "title": title, "variants": [{"price": price, "available": True, "sku": h}], "images": []}
class _Resp:
    def __init__(self, code, products=None, bad_json=False): self.status_code, self._p, self._bad = code, products, bad_json
    def json(self):
        if self._bad:
            raise ValueError("bad json")
        return {"products": self._p}
def _getter(pages):
    def get(url, timeout=None, headers=None):
        r = pages[int(url.rsplit("page=", 1)[1]) - 1]
        if isinstance(r, Exception):
            raise r
        return r
    return get
r = sc.scrape_shopify_catalog(_cfg, get=_getter([_Resp(200, [_prod("a"), _prod("gc", title="Gift Card")]),
                                                 _Resp(200, [_prod("b")]), _Resp(200, [])]))
assert r["complete"] and r["reason"] == "ok", r["reason"]
assert {p["product_url"] for p in r["products"]} == {"https://x.com/products/a", "https://x.com/products/b"}
assert "https://x.com/products/gc" in r["seen_urls"]  # gift card skip hua par "seen" hai - delisted nahi
r = sc.scrape_shopify_catalog(_cfg, get=_getter([_Resp(200, [_prod("a")]), _Resp(429)]))
assert not r["complete"] and r["reason"] == "status 429" and len(r["products"]) == 1, r
r = sc.scrape_shopify_catalog(_cfg, get=_getter([_Resp(200, [_prod("a")]), _rq.ConnectionError("down")]))
assert not r["complete"] and r["reason"] == "error" and len(r["products"]) == 1, r
r = sc.scrape_shopify_catalog(_cfg, get=_getter([_Resp(200, [_prod("a")]), _Resp(200, bad_json=True)]))
assert not r["complete"] and r["reason"] == "error", r
r = sc.scrape_shopify_catalog(_cfg, get=_getter([_Resp(200, [_prod(f"p{i}")]) for i in range(sc.MAX_PAGES)]))
assert not r["complete"] and r["reason"] == "cap" and len(r["products"]) == sc.MAX_PAGES, r
_orig = sc.scrape_shopify_catalog
sc.scrape_shopify_catalog = lambda cfg: {"products": [1, 2], "seen_urls": set(), "complete": True, "reason": "ok"}
assert sc.scrape_shopify(_cfg) == [1, 2]  # purana contract: sirf products list
sc.scrape_shopify_catalog = _orig

# delisted.plan_delisted: sirf unseen in-stock rows, guards pe kuch nahi
import delisted as dl
_T0 = "2026-10-05T10:00:00+00:00"
def _row(i, url=True, in_stock=True, scraped="2026-10-04T10:00:00+00:00"):
    return {"id": i, "product_url": f"https://x.com/products/p{i}" if url else None, "in_stock": in_stock, "scraped_at": scraped}
_rows = [_row(i) for i in range(10)] + [_row(10, in_stock=False), _row(11, url=False),
                                        _row(12, scraped="2026-10-05T10:05:00+00:00")]
_seen = {f"https://x.com/products/p{i}" for i in range(8)}
m, why = dl.plan_delisted(_rows, _seen, _T0)
assert why == "ok" and sorted(r["id"] for r in m) == [8, 9], (why, m)  # 10 sold out, 11 bina URL, 12 isi run ka
m, why = dl.plan_delisted(_rows, {f"https://x.com/products/p{i}" for i in range(4)}, _T0)  # 4 seen < 50% of 11
assert m == [] and why.startswith("seen"), why
_seen2 = (_seen - {f"https://x.com/products/p{i}" for i in range(4)}) | {f"https://x.com/new{i}" for i in range(5)}
m, why = dl.plan_delisted(_rows, _seen2, _T0)
assert m == [] and why.startswith("mark"), why  # 6 of 11 = 55% > 30%
assert dl.plan_delisted([_row(1, in_stock=False)], set(), _T0) == ([], "no in-stock rows")
assert dl.plan_delisted(_rows, _seen, "2026-10-05T10:00:00Z")[1] == "ok"  # Z suffix bhi chale

# delisted.mark_unseen_sold_out: dry = koi write nahi; "1" = sirf planned rows, saare sizes false
class _DQ:
    def __init__(self, db, table): self.db, self.table, self.filters, self.op, self.payload = db, table, [], None, None
    def select(self, *_a): return self
    def eq(self, c, v): self.filters.append((c, v)); return self
    def gt(self, *_a): return self
    def order(self, *_a): return self
    def limit(self, *_a): return self
    def update(self, d): self.op, self.payload = "update", d; return self
    def insert(self, rows): self.op, self.payload = "insert", rows; return self
    def execute(self):
        if self.op:
            self.db.calls.append((self.table, self.op, self.payload, self.filters))
            rid = dict(self.filters).get("id")
            hit = self.op == "update" and rid not in self.db.relisted
            return type("R", (), {"data": [{"id": rid}] if hit else []})()
        return type("R", (), {"data": [dict(r) for r in self.db.rows]})()
class _DB:
    def __init__(self, rows, relisted=()): self.rows, self.calls, self.relisted = rows, [], set(relisted)
    def table(self, t): return _DQ(self, t)
_vrows = [{**r, "site": "x", "sku": f"s{r['id']}", "name": f"N{r['id']}",
           "variants": [{"size": "S", "in_stock": True, "price": 10}, {"size": "M", "in_stock": True, "price": 10}]}
          for r in _rows]
_logs = []
res = dl.mark_unseen_sold_out(_DB(_vrows), "x", _seen, _T0, log=_logs.append)
assert res["planned"] == 2 and res["marked"] == 0 and res["reason"] == "ok", res
_bkp = tempfile.mktemp(suffix=".json")
_db = _DB(_vrows)  # mode "1" bina backup path -> kuch nahi likhta (safe-writes)
res = dl.mark_unseen_sold_out(_db, "x", _seen, _T0, mode="1", log=_logs.append)
assert res["marked"] == 0 and res["reason"] == "no backup path" and _db.calls == [], res
_db = _DB(_vrows)
res = dl.mark_unseen_sold_out(_db, "x", _seen, _T0, mode="1", backup_path=_bkp, log=_logs.append)
assert sorted(r["id"] for r in _json.load(open(_bkp))) == [8, 9]  # backup pehle, planned rows ka
_ups = [c for c in _db.calls if c[1] == "update"]
assert res["marked"] == 2 and sorted(dict(c[3])["id"] for c in _ups) == [8, 9], (res, _ups)
assert all(c[0] == "products" and ("in_stock", True) in c[3] for c in _ups)  # re-list race guard
assert all(not v["in_stock"] for c in _ups for v in c[2]["variants"]) and all(c[2]["in_stock"] is False for c in _ups)
assert all("price" not in c[2] and "selling_price_inr" not in c[2] for c in _ups)  # price nahi chhoota
_ins = [c for c in _db.calls if c[1] == "insert"]
assert len(_ins) == 1 and _ins[0][0] == "product_changes" and [x["change_type"] for x in _ins[0][2]] == ["delisted"] * 2
_db = _DB(_vrows)  # guard fail -> mode "1" bhi kuch nahi likhta
res = dl.mark_unseen_sold_out(_db, "x", {"https://x.com/products/p0"}, _T0, mode="1", backup_path=_bkp,
                              log=_logs.append)
assert res["marked"] == 0 and _db.calls == [], res
_db = _DB(_vrows)  # deadline beet chuki -> koi update nahi, phir bhi crash nahi
res = dl.mark_unseen_sold_out(_db, "x", _seen, _T0, mode="1", deadline=1, backup_path=_bkp, log=_logs.append)
assert res["marked"] == 0 and _db.calls == [], res
_db = _DB(_vrows, relisted={9})  # row 9 beech mein dobara listed -> update 0 rows -> marked/log mein nahi
res = dl.mark_unseen_sold_out(_db, "x", _seen, _T0, mode="1", backup_path=_bkp, log=_logs.append)
_ins = [c for c in _db.calls if c[1] == "insert"]
assert res["marked"] == 1 and [x["product_url"] for x in _ins[0][2]] == ["https://x.com/products/p8"], (res, _ins)
# naive scraped_at (timestamp bina tz) bhi chale, crash nahi
_nv = [_row(i, scraped="2026-10-04T10:00:00") for i in range(4)]
m, why = dl.plan_delisted(_nv, {f"https://x.com/products/p{i}" for i in range(1, 4)}, _T0)
assert why == "ok" and [r["id"] for r in m] == [0], (why, m)

# MARK_DELISTED mode + should_mark (main.run ka gate)
assert [dl.mark_mode(v) for v in (None, "", "dry", "1", "0", "off", "yes")] == ["dry", "dry", "dry", "1", "off", "off", "dry"]
_shop = {"platform": "shopify", "name": "x"}
_ok = {"complete": True}
assert dl.should_mark(_shop, _ok, 0, deadline=100, mode="dry", now=50)
assert not dl.should_mark(_shop, {"complete": False}, 0, 100, "1", now=50)           # adhoora scrape
assert not dl.should_mark({"name": "y", "use_firecrawl": True}, _ok, 0, 100, "1", now=50)  # firecrawl site
assert not dl.should_mark(_shop, _ok, 3, 100, "1", now=50)                             # kuch save nahi hua
assert not dl.should_mark(_shop, _ok, 0, 100, "1", now=150)                            # deadline
assert not dl.should_mark(_shop, _ok, 0, 100, "off", now=50)
assert not dl.should_mark(_shop, None, 0, 100, "1", now=50)

# main.py offline import (dummy env, koi network nahi) - wiring syntax/import sahi hai
os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"] = "http://localhost:1", "a.b.c"
import contextlib
import io as _io
with contextlib.redirect_stdout(_io.StringIO()):
    import main as _main
assert _main.delisted is dl and hasattr(_main, "scrape_shopify_catalog")
os.environ["SUPABASE_URL"] = os.environ["SUPABASE_SERVICE_KEY"] = ""

print("ok")
