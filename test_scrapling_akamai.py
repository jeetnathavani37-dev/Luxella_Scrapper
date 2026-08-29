"""
test_scrapling_akamai.py

Tests whether Scrapling's stealthy_headers can bypass Akamai bot protection
on Michael Kors and Coach Outlet WITHOUT a residential proxy — run from
GitHub Actions to see if the runner IP gets blocked where a local/sandbox
IP didn't.

Usage:
    pip install "scrapling[fetchers]"
    scrapling install
    python test_scrapling_akamai.py

Optional: set WEBSHARE_PROXY env var (format: http://user:pass@host:port)
to also run the same tests through your existing proxy for comparison.
"""

import os
import time
import json
from scrapling.fetchers import Fetcher

RESULTS = []

TARGETS = [
    {"brand": "Michael Kors", "label": "homepage", "url": "https://www.michaelkors.com/"},
    {"brand": "Michael Kors", "label": "category_page", "url": "https://www.michaelkors.com/women/handbags/"},
    {
        "brand": "Michael Kors",
        "label": "product_grid_api",
        "url": (
            "https://www.michaelkors.com/on/demandware.store/"
            "Sites-mk_us-Site/en_US/Search-UpdateGrid"
            "?cgid=womens-handbags&start=0&sz=24"
        ),
    },
    {"brand": "Coach Outlet", "label": "homepage", "url": "https://www.coachoutlet.com/"},
    {"brand": "Coach", "label": "homepage", "url": "https://www.coach.com/"},
]


def run_test(target, proxy=None):
    kwargs = {"timeout": 20, "stealthy_headers": True}
    if proxy:
        kwargs["proxy"] = proxy

    t0 = time.time()
    try:
        page = Fetcher.get(target["url"], **kwargs)
        elapsed = round(time.time() - t0, 2)
        body_len = len(page.body or b"")
        looks_blocked = body_len < 5000 or page.status in (403, 429, 999)

        product_count = None
        if target["label"] == "product_grid_api" and page.status == 200:
            names = page.css(".product-name::text, .pdp-link a::text").getall()
            product_count = len([n for n in names if n.strip()])

        result = {
            "brand": target["brand"],
            "label": target["label"],
            "url": target["url"],
            "proxy_used": bool(proxy),
            "status": page.status,
            "time_s": elapsed,
            "body_length": body_len,
            "looks_blocked": looks_blocked,
            "product_names_found": product_count,
        }
    except Exception as e:
        result = {
            "brand": target["brand"],
            "label": target["label"],
            "url": target["url"],
            "proxy_used": bool(proxy),
            "status": "EXCEPTION",
            "error": str(e),
            "time_s": round(time.time() - t0, 2),
        }

    RESULTS.append(result)
    return result


def print_result(r):
    status_icon = "OK" if not r.get("looks_blocked") and r.get("status") == 200 else "BLOCKED"
    if r["status"] == "EXCEPTION":
        status_icon = "ERROR"
    proxy_tag = "[PROXY]" if r["proxy_used"] else "[NO PROXY]"
    line = f"{status_icon} {proxy_tag} {r['brand']} / {r['label']}: status={r['status']}, time={r['time_s']}s"
    if "body_length" in r:
        line += f", body_len={r['body_length']}"
    if r.get("product_names_found") is not None:
        line += f", products_found={r['product_names_found']}"
    if "error" in r:
        line += f", error={r['error']}"
    print(line)


def main():
    print("=" * 70)
    print("SCRAPLING AKAMAI BYPASS TEST - NO PROXY")
    print("=" * 70)
    for target in TARGETS:
        r = run_test(target, proxy=None)
        print_result(r)
        time.sleep(1)

    proxy = os.environ.get("WEBSHARE_PROXY")
    if proxy:
        print()
        print("=" * 70)
        print("SCRAPLING TEST - WITH WEBSHARE PROXY (comparison)")
        print("=" * 70)
        for target in TARGETS:
            r = run_test(target, proxy=proxy)
            print_result(r)
            time.sleep(1)
    else:
        print()
        print("(Skipped proxy comparison - set WEBSHARE_PROXY env var to enable)")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    no_proxy_results = [r for r in RESULTS if not r["proxy_used"]]
    blocked_no_proxy = [r for r in no_proxy_results if r.get("looks_blocked") or r["status"] != 200]
    print(f"No-proxy tests: {len(no_proxy_results)}")
    print(f"Blocked/failed without proxy: {len(blocked_no_proxy)}")
    if not blocked_no_proxy:
        print(">>> ALL TARGETS ACCESSIBLE WITHOUT PROXY FROM THIS RUNNER <<<")
    else:
        print(">>> SOME TARGETS STILL BLOCKED WITHOUT PROXY - proxy still needed for these:")
        for r in blocked_no_proxy:
            print(f"    - {r['brand']} / {r['label']}")

    print()
    print("--- FULL JSON RESULTS ---")
    print(json.dumps(RESULTS, indent=2))

    with open("scrapling_akamai_test_results.json", "w") as f:
        json.dump(RESULTS, f, indent=2)


if __name__ == "__main__":
    main()
