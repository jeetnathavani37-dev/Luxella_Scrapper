# Luxella MCP server — notes

`luxella_mcp.py` ek stdio MCP server hai (mcp v2 `MCPServer`) jo Claude aur Hermes dono se chalta hai.
Self-check: `.venv/bin/python test_luxella_mcp.py`

## 4 tools

| Tool | Kya karta hai | Writes? |
|---|---|---|
| `luxella_sync_catalog(limit=50, confirm=False)` | Next batch ka preview: kitne create honge, kitne duplicate skip, kitne price/stock update | Sirf `confirm=True` pe |
| `luxella_check_availability(limit, offset)` | Source pe out-of-stock, lekin Shopify pe abhi bhi in-stock (`last_synced_in_stock=true`) | No |
| `luxella_price_report(brand, site, pushed_only, limit, offset)` | Source price vs landed cost vs selling price, margin, `store_stale` flag | No |
| `luxella_query(table, columns, eq, ilike, order_by, desc, limit, offset)` | `products` / `product_changes` pe read-only lookup | No |

## Confirm flag

- Default sab kuch read-only / dry-run hai.
- Shopify pe sirf `luxella_sync_catalog` likhta hai, aur sirf `confirm=True` pe.
- `confirm=True` pe ye repo ka hi `shopify_push.run()` + `shopify_sync.run()` chalata hai (`BATCH_SIZE = limit`), koi alag push code nahi. Isliye duplicate-check aur Supabase ke `pushed_to_shopify` / `last_synced_*` flags wahi rehte hain jo GitHub Actions mein.
- Pipeline ka `print()` output capture hota hai (stdout = MCP protocol channel) aur `log_tail` mein return hota hai.

## ponytail comment (drift risk)

`luxella_mcp.py` → `price_stock_changes()` (line ~83):

```
# ponytail: shopify_sync.run() ki inline logic ki copy - wahan badle to yahan bhi badlo
```

Dry-run preview `shopify_sync.run()` ka price/compare-at/stock change check copy karta hai.
`shopify_sync.py` mein sync rule badlo to yahan bhi update karo, warna preview aur actual run alag honge.
Same tarah `is_duplicate()` = `shopify_push.run()` ka duplicate rule (`existing <= this_price`).

## `price` column assumption

`luxella_price_report` `products.price` (source retailer price, `currency` mein) select karta hai.
Ye live schema se verify NAHI hua — `db.save_product()` scraper ka `price` field seedha insert karta hai, usi se assume kiya.
Pehli live run pe column naam check karna hai; galat hua to tool clear error dega (`ToolError` mein Supabase ka message).

## Env vars (`~/.luxella.env`, `chmod 600`)

| Var | Zaroori | Note |
|---|---|---|
| `SUPABASE_URL` | Haan | `https://bkxzkrbhqpwosqecndnx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Haan | service_role key |
| `SHOPIFY_TOKEN` | Writes ke liye (ya neeche wale dono) | Static `shpat_...` token; set ho to client-credentials grant skip |
| `SHOPIFY_CLIENT_ID` + `SHOPIFY_CLIENT_SECRET` | `SHOPIFY_TOKEN` ki jagah | Pipeline wala client-credentials grant |
| `SHOPIFY_STORE_DOMAIN` | Nahi | Default `luxella-9299.myshopify.com` |

## Register

Claude Code (already done, user scope, name `luxella`):

```
claude mcp add luxella -s user -- ~/repos/Luxella_Scrapper/.venv/bin/python ~/repos/Luxella_Scrapper/luxella_mcp.py
```

Hermes: same command apne MCP server config mein daalo.
