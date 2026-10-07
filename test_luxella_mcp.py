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
# single-variant Shopify listing (2026-10-06): "Default Title" product -> plan mein item nahi (na write, na signature)
_shop["P3"] = [{"inventory_item_id": "k1", "size": "Default Title", "available": 10}]
_p3 = {**_p1, "id": 14, "shopify_product_id": "P3"}
items3, totals3 = rv.plan("t", [_p1, _p3])
assert [it["row"]["id"] for it in items3] == [11], items3          # P3 ka koi item nahi -> apply signature nahi likhega
assert totals3["single_variant_on_shopify"] == 1 and totals3["unmatched_sizes"] == 0, totals3
assert totals3["sizes_checked"] == len(sizes13), totals3            # unmatched share mein single-variant nahi gina
# repair stale guard (2026-10-06): purane / bina scraped_at wale products ko repair chhoota nahi
from datetime import datetime as _dt, timezone as _tz
_now = _dt(2026, 10, 6, 12, 0, tzinfo=_tz.utc)
_fr = {"id": 21, "site": "a", "scraped_at": "2026-10-05T12:00:00+00:00"}      # 1 din
_edge = {"id": 22, "site": "a", "scraped_at": "2026-10-03T12:00:00+00:00"}    # theek 3 din = abhi bhi fresh
_old = {"id": 23, "site": "b", "scraped_at": "2026-10-01T12:00:00+00:00"}     # 5 din
_naive = {"id": 24, "site": "b", "scraped_at": "2026-10-06T10:00:00"}         # naive = UTC, 2 ghante
_none = {"id": 25, "site": "c", "scraped_at": None}
_f, _s = rv.split_fresh([_fr, _edge, _old, _naive, _none], 3, now=_now)
assert [r["id"] for r in _f] == [21, 22, 24] and [r["id"] for r in _s] == [23, 25], (_f, _s)
assert rv.split_fresh([_old], 7, now=_now)[0] == [_old]  # --max-age-days 7 se 5-din wala andar
import inspect as _inspect
assert "scraped_at" in _inspect.getsource(rv.fetch_candidates)  # warna sab stale dikhenge aur repair kuch nahi karega
# repair read retry (2026-10-06 run 37489368238 ek Shopify 500 pe gira): 5xx/timeout pe dobara, 4xx pe turant fail
import requests as _rq
def _http(code):
    r = _rq.Response(); r.status_code = code
    return _rq.HTTPError(f"{code}", response=r)
_orig_gql, _orig_sleep = rv.ss.shopify_graphql, rv.time.sleep
rv.time.sleep = lambda s: None
_calls = []
def _flaky(tok, q, v):
    _calls.append(1)
    if len(_calls) == 1:
        raise _http(500)
    if len(_calls) == 2:
        raise _rq.Timeout("t")
    return {"nodes": []}
rv.ss.shopify_graphql = _flaky
assert rv.read_graphql("t", "q", {}) == {"nodes": []} and len(_calls) == 3
_calls.clear()
def _always500(tok, q, v): _calls.append(1); raise _http(503)
rv.ss.shopify_graphql = _always500
try:
    rv.read_graphql("t", "q", {}); raise AssertionError("4 baar 503 ke baad bhi raise hona chahiye")
except _rq.HTTPError:
    assert len(_calls) == 4
_calls.clear()
def _auth(tok, q, v): _calls.append(1); raise _http(401)
rv.ss.shopify_graphql = _auth
try:
    rv.read_graphql("t", "q", {}); raise AssertionError("401 pe retry nahi")
except _rq.HTTPError:
    assert len(_calls) == 1
rv.ss.shopify_graphql, rv.time.sleep = _orig_gql, _orig_sleep
assert "read_graphql(token, SIZES_QUERY" in open(rv.__file__).read()  # bulk reader (test mein lambda se badla) asli mein retry use kare
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

# relist_sizes (2026-10-06): bina-size listing me asli Size variants - targets, plan filter, write order,
# rollback, restore checks, main() guards. Module globals jo badle wo aakhir mein wapas.
import relist_sizes as rl
_saved = (rl.ss.shopify_graphql, rl.ss.set_size_quantities, rl.read_shopify, rl.read_one)
_rr = {**partial, "id": 31, "site": "aloyoga", "name": "ALO Runner", "shopify_product_id": "R1"}  # 13 sizes, 6+7 sold out
_t = rl.build_targets(_rr)
assert [x["size"] for x in _t] == sizes13 and len(_t) == 13, _t
assert {x["size"]: x["qty"] for x in _t}["6"] == 0 and {x["size"]: x["qty"] for x in _t}["5"] == 10
assert all(x["sku"] == f"LX-31-{x['size']}" for x in _t) and all(float(x["price"]) > 0 for x in _t)  # sku fallback
assert rl.build_targets({**_rr, "price": 0}) == []                                         # price 0 -> relist nahi
assert rl.build_targets({**_rr, "variants": _rr["variants"][:1]}) == []                    # single size -> nahi
assert rl.build_targets({**_rr, "name": "ALO e-Gift Card"}) == []                          # gift card kabhi nahi
_s1 = {"options": [{"id": "o1", "name": "Title"}], "variant_id": "gid://shopify/ProductVariant/9", "title": "Default Title",
       "price": "25699.00", "compare_at": None, "sku": "OLD", "inventory_item_id": "77", "available": 0}
rl.read_shopify = lambda tok, pids: {"R1": _s1, "R2": {**_s1, "title": "6"}}  # R2 = adhoora pichla run
_items, _tot = rl.plan("t", [_rr, {**_rr, "id": 32, "shopify_product_id": "R2"}, {**_rr, "id": 33, "shopify_product_id": "R3"}])
assert [it["row"]["id"] for it in _items] == [31], _items
assert _tot["to_relist"] == 1 and _tot["skipped_not_default_title"] == 1 and _tot["not_single_variant_on_shopify"] == 1, _tot
assert _tot["variants_to_create"] == 12 and _tot["sold_out_becomes_buyable"] == 1, _tot
_ev = []
_fail_on = set()
def _fake_gql(tok, q, v):
    k = q.split("{", 2)[1].split("(")[0].strip()
    _ev.append(k)
    if k in _fail_on:
        return {k: {"userErrors": [{"message": "boom"}]}}
    if k == "productOptionsCreate":
        return {k: {"product": {"options": [{"id": "oS", "name": "Size"}],
                                "variants": {"nodes": [{"id": _s1["variant_id"], "title": "5"}]}}, "userErrors": []}}
    return {k: {"userErrors": []}}
rl.ss.shopify_graphql = _fake_gql
rl.ss.set_size_quantities = lambda tok, ch, ref: _ev.append(("stock", ch))
rl.read_one = lambda tok, pid: dict(_s1)  # fresh re-read (plan purana ho sakta hai)
class _SB3:
    def table(self, _):
        class Q:
            def update(q, d): _ev.append(("sig", d["last_synced_variant_stock"] is not None)); return q
            def eq(q, *a): return q
            def execute(q): return None
        return Q()
class _BK:
    def write(self, x): _ev.append("backup")
    def flush(self): pass
rl.relist_one(_SB3(), "t", _items[0], _BK())
assert _ev[0] == "backup" and _ev[1] == "productOptionsCreate" and _ev[-1] == ("sig", True), _ev     # backup pehle, signature aakhir
assert ("stock", [("77", 0, 10)]) in _ev and "productVariantsBulkCreate" in _ev, _ev                  # size "5" 0 -> 10 CAS
# halat badli (ab Default Title nahi) -> Skip, koi write/backup nahi
_ev.clear(); rl.read_one = lambda tok, pid: {**_s1, "title": "5"}
try:
    rl.relist_one(_SB3(), "t", _items[0], _BK()); raise AssertionError("expected Skip")
except rl.Skip:
    pass
assert _ev == [], _ev
rl.read_one = lambda tok, pid: dict(_s1)
# Shopify ne alag pehla variant diya -> RelistError, koi variant create/signature nahi
_ev.clear(); rl.read_one = lambda tok, pid: {**_s1, "variant_id": "gid://shopify/ProductVariant/OTHER"}
try:
    rl.relist_one(_SB3(), "t", _items[0], _BK()); raise AssertionError("expected RelistError")
except rl.RelistError:
    pass
assert not any(isinstance(e, tuple) and e[0] == "sig" for e in _ev) and "productVariantsBulkCreate" not in _ev, _ev
rl.read_one = lambda tok, pid: dict(_s1)
# bulkCreate fail (option ban chuka) -> turant rollback (Size option delete + purana price/SKU), signature nahi
_ev.clear(); _fail_on = {"productVariantsBulkCreate"}
try:
    rl.relist_one(_SB3(), "t", _items[0], _BK()); raise AssertionError("expected RelistError")
except rl.RelistError as e:
    assert "rolled back" in str(e), e
assert "productOptionsDelete" in _ev and _ev.index("productOptionsDelete") > _ev.index("productVariantsBulkCreate"), _ev
assert not any(isinstance(e, tuple) and e[0] == "sig" for e in _ev), _ev
_fail_on = set()
# restore: delete se PEHLE check; pehle se restored / pehla variant original nahi -> skip, koi delete nahi
_rbk = tempfile.mktemp(suffix=".jsonl")
with open(_rbk, "w") as _f:
    _f.write(_json.dumps({"supabase_id": 31, "product_id": "R1", "before": _s1}) + "\n")
    _f.write(_json.dumps({"supabase_id": 32, "product_id": "R2", "before": _s1}) + "\n")
def _node(opts, first_id):
    return {"id": "x", "options": [{"id": "oS", "name": n} for n in opts],
            "variants": {"nodes": [{"id": first_id, "title": "5", "price": "1", "compareAtPrice": None,
                                    "inventoryItem": {"id": "gid://shopify/InventoryItem/77", "sku": "s",
                                                      "inventoryLevel": {"quantities": [{"quantity": 10}]}}}]}}
def _restore_gql(nodes):
    def g(tok, q, v):
        k = q.split("{", 2)[1].split("(")[0].strip()
        if k == "nodes":
            return {"nodes": [nodes[v["ids"][0].rsplit("/", 1)[1]]]}
        _ev.append(k)
        return {k: {"userErrors": []}}
    return g
_ev.clear()
rl.ss.shopify_graphql = _restore_gql({"R1": _node(["Title"], _s1["variant_id"]), "R2": _node(["Size"], "gid://shopify/ProductVariant/X")})
_ok, _sk = rl.restore(_SB3(), "t", _rbk)
assert _ok == 0 and [x[0] for x in _sk] == [31, 32] and "productOptionsDelete" not in _ev, (_ok, _sk, _ev)
_ev.clear()
rl.ss.shopify_graphql = _restore_gql({"R1": _node(["Size"], _s1["variant_id"]), "R2": _node(["Size"], _s1["variant_id"])})
_ok, _sk = rl.restore(_SB3(), "t", _rbk, only_id=31)                                    # sirf ek product
assert _ok == 1 and _ev.count("productOptionsDelete") == 1 and ("stock", [("77", 10, 0)]) in _ev, (_ok, _ev)
# main() guards: --restore "" kabhi relist pe nahi giregi; --confirm bina limit/only-id/--all -> abort
import sys as _sys
for _argv in (["relist_sizes.py", "--restore", "", "--confirm"], ["relist_sizes.py", "--confirm"]):
    _sys.argv = _argv
    try:
        rl.main(); raise AssertionError(f"expected SystemExit for {_argv}")
    except SystemExit as e:
        assert "ABORT" in str(e.code), e.code
_sys.argv = ["test_luxella_mcp.py"]
rl.ss.shopify_graphql, rl.ss.set_size_quantities, rl.read_shopify, rl.read_one = _saved

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

# daily_report (spec 2026-10-07): status rules, missing source -> n/a + partial, bad pehle, phone <= 12 lines, 7-day avg
import daily_report as dr
from datetime import datetime as _dtm, date as _date
assert dr.kpi_status(0, 0) == "ok" and dr.kpi_status(3, 0) == "bad" and dr.kpi_status(5, None) == "-"
assert dr.kpi_status(None, 0) == dr.NA
_full = {"supabase": {"pushed": 10, "live": 8, "oos": 2, "price0": 0, "stale3d": 1, "scraped_24h": 9, "changes_24h": 4},
         "shopify": {"active": 8, "oos_live": 0}, "actions": {"failed": [], "cancelled": 0, "success": 3, "running": 0},
         "approvals": {"count": 0, "top": []}, "at": {}}
_now = _dtm(2026, 10, 7, 2, 30)
_r = dr.build_report(_full, [], _now)
assert _r.status == "ok" and _r.priority == "default" and len(_r.short.splitlines()) == 3, _r.short
assert _r.snapshot["id"] == "d-2026-10-07T02:30" and _r.snapshot["kpis"]["products live"] == 8
_r = dr.build_report({**_full, "actions": None}, [], _now)                    # GitHub down -> report phir bhi
assert _r.status == "partial" and "actions " + dr.NA in _r.text and "failed syncs | " + dr.NA in _r.text
assert dr.build_report({"at": {}}, [], _now).status == "failed"
_bad = {**_full, "shopify": {"active": 8, "oos_live": 5}, "supabase": {**_full["supabase"], "price0": 3},
        "actions": {"failed": [{"name": f"job{i}", "url": "u"} for i in range(20)], "cancelled": 2, "success": 0, "running": 0}}
_r = dr.build_report(_bad, [], _now)
_sl = _r.short.splitlines()
assert _r.priority == "high" and len(_sl) <= dr.SHORT_MAX_LINES, _sl
assert _sl[1].startswith("OOS-but-live") and _sl[2].startswith("failed syncs") and _sl[3].startswith("price 0"), _sl
assert "token" not in _r.short.lower()
_hist = [{"id": f"d{i}", "at": f"2026-10-0{i}T02:30:00", "kpis": {"products live": 10 * i}} for i in range(1, 7)]
assert dr.seven_day_avg(_hist, "products live", _date(2026, 10, 7)) is None                      # sirf 6 din
_hist.append({"id": "d0", "at": "2026-09-30T02:30:00", "kpis": {"products live": None}})        # 7wa din, value None
assert dr.seven_day_avg(_hist, "products live", _date(2026, 10, 7)) == 35                       # None din chhoda
_hist.append({"id": "dx", "at": "2026-10-07T01:00:00", "kpis": {"products live": 999}})         # aaj gina nahi
assert dr.seven_day_avg(_hist, "products live", _date(2026, 10, 7)) == 35
# daily_report main(): --dry-run kuch nahi likhta/bhejta, --no-push log likhta par push nahi, token file gayab -> partial
import os as _os2
import tempfile as _tf2
import json as _js2
import packages.core.approvals as _ap
_ops = _tf2.mkdtemp(); _old_ops = _os2.environ.get("LUXELLA_OPS_DIR"); _os2.environ["LUXELLA_OPS_DIR"] = _ops
_sent = []
_orig_urlopen = _ap.urllib.request.urlopen
class _Resp:
    def read(self): return b""
_ap.urllib.request.urlopen = lambda req, timeout=10: (_sent.append(req), _Resp())[1]
_os2.environ["LUXELLA_NTFY_TOPIC"] = "test-topic"
_fake = {"supabase": lambda: _full["supabase"], "shopify": lambda: _full["shopify"],
         "actions": lambda: _full["actions"], "approvals": lambda: {"count": 0, "top": []}}
assert dr.main(["--dry-run"], readers=_fake, now=_now) == 0
assert _os2.listdir(_ops) == [] and _sent == []                                   # dry-run: kuch nahi
assert dr.main(["--no-push"], readers=_fake, now=_now) == 0
assert sorted(_os2.listdir(_ops)) == ["agent_runs.jsonl", "daily_report.jsonl"] and _sent == []
dr.RETRY_SLEEP = 0
_flaky_n = []
_fake_flaky = {**_fake, "supabase": lambda: _full["supabase"] if _flaky_n.append(1) or len(_flaky_n) > 1 else 1 / 0}
assert dr.gather(_now, _fake_flaky)["supabase"] == _full["supabase"] and len(_flaky_n) == 2  # ek retry
_fake_bad = {**_fake, "actions": lambda: dr.read_actions("/nonexistent/token", "o/r", _now)}  # token file gayab
assert dr.main([], readers=_fake_bad, now=_now) == 0 and len(_sent) == 1
_runs = [_js2.loads(x) for x in open(_os2.path.join(_ops, "agent_runs.jsonl"))]
assert [r["status"] for r in _runs] == ["ok", "partial"] and _runs[-1]["outputs"]["pushed"] is True
_body = _sent[0].data.decode()
assert "actions: " + dr.NA in _body and "Bearer" not in _body and "/nonexistent" not in _body
assert _sent[0].get_header("Priority") == "default" and _sent[0].full_url.endswith("/test-topic")
_ap.urllib.request.urlopen = _orig_urlopen
del _os2.environ["LUXELLA_NTFY_TOPIC"]
if _old_ops is None:
    del _os2.environ["LUXELLA_OPS_DIR"]
else:
    _os2.environ["LUXELLA_OPS_DIR"] = _old_ops
# read_shopify: count EXACT nahi (10k cap) -> fail, taaki galat number na jaaye
import repair_variant_stock as _rv2
_orig_rg = _rv2.read_graphql
_rv2.read_graphql = lambda t, q, v: {"active": {"count": 10000, "precision": "AT_LEAST"}, "oos_live": {"count": 1, "precision": "EXACT"}}
try:
    dr.read_shopify("t"); raise AssertionError("AT_LEAST count accept nahi hona chahiye")
except RuntimeError:
    pass
_rv2.read_graphql = lambda t, q, v: {"active": {"count": 52650, "precision": "EXACT"}, "oos_live": {"count": 7, "precision": "EXACT"}}
assert dr.read_shopify("t") == {"active": 52650, "oos_live": 7} and "limit: null" in dr.SHOPIFY_COUNTS
_rv2.read_graphql = _orig_rg

print("ok")
