"""
test_scrapling_akamai.py

Tests whether Scrapling's stealthy_headers can bypass bot protection
(Akamai and others) on EVERY site configured in sites.py — WITHOUT a
residential proxy. Run from GitHub Actions to see which sites the runner
can access cleanly and which still need a proxy or browser mode.

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
from sites import SITES

RESULTS = []


def build_targets():
    """Build one homepage/start-url target per site from sites.py."""
    targets = []
    for site in SITES:
        name = site["name"]
        if "start_urls" in site:
            url = site["start_urls"][0]
        elif "domain" in site:
            url = site["domain"].rstrip("/") + "/"
        else:
            continue
        targets.append({
            "brand": name,
            "label": "homepage",
            "url": url,
            "known_needs_proxy": site.get("needs_proxy", False),
        })
    return targets


TARGETS = build_targets()

# Extra known Akamai/SFCC-style targets not yet in sites.py, worth checking
EXTRA_TARGETS = [
    {"brand": "Tory Burch", "label": "homepage", "url": "https://www.toryburch.com/", "known_needs_proxy": None},
    {"brand": "Christian Louboutin", "label": "homepage", "url": "https://us.christianlouboutin.com/", "known_needs_proxy": None},
    {"brand": "Garmin", "label": "homepage", "url": "https://www.garmin.com/en-US/", "known_needs_proxy": None},
]
TARGETS = TARGETS + EXTRA_TARGETS


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

        result = {
            "brand": target["brand"],
            "label": target["label"],
            "url": target["url"],
            "known_needs_proxy": target.get("known_needs_proxy"),
            "proxy_used": bool(proxy),
            "status": page.status,
            "time_s": elapsed,
            "body_length": body_len,
            "looks_blocked": looks_blocked,
        }
    except Exception as e:
        result = {
            "brand": target["brand"],
            "label": target["label"],
            "url": target["url"],
            "known_needs_proxy": target.get("known_needs_proxy"),
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
    flag = " (was marked needs_proxy)" if r.get("known_needs_proxy") else ""
    line = f"{status_icon} {proxy_tag} {r['brand']}{flag}: status={r['status']}, time={r['time_s']}s"
    if "body_length" in r:
        line += f", body_len={r['body_length']}"
    if "error" in r:
        line += f", error={r['error']}"
    print(line)


def main():
    print("=" * 70)
    print(f"SCRAPLING BYPASS TEST - NO PROXY - {len(TARGETS)} SITES")
    print("=" * 70)
    for target in TARGETS:
        r = run_test(target, proxy=None)
        print_result(r)
        time.sleep(0.5)  # be polite between requests

    proxy = os.environ.get("WEBSHARE_PROXY")
    if proxy:
        print()
        print("=" * 70)
        print("RE-TESTING BLOCKED SITES - WITH WEBSHARE PROXY (comparison)")
        print("=" * 70)
        blocked_targets = [
            t for t in TARGETS
            for r in RESULTS
            if r["brand"] == t["brand"] and r["label"] == t["label"]
            and not r["proxy_used"] and (r.get("looks_blocked") or r["status"] != 200)
        ]
        for target in blocked_targets:
            r = run_test(target, proxy=proxy)
            print_result(r)
            time.sleep(0.5)
    else:
        print()
        print("(Skipped proxy comparison - set WEBSHARE_PROXY env var to enable)")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    no_proxy_results = [r for r in RESULTS if not r["proxy_used"]]
    blocked_no_proxy = [
        r for r in no_proxy_results
        if r.get("looks_blocked") or r["status"] != 200
    ]
    ok_no_proxy = [r for r in no_proxy_results if r not in blocked_no_proxy]

    print(f"Total sites tested: {len(no_proxy_results)}")
    print(f"OK without proxy: {len(ok_no_proxy)}")
    print(f"Blocked/failed without proxy: {len(blocked_no_proxy)}")

    if blocked_no_proxy:
        print()
        print(">>> SITES STILL NEEDING PROXY / BROWSER MODE:")
        for r in blocked_no_proxy:
            print(f"    - {r['brand']} ({r['label']}): status={r['status']}")
    else:
        print(">>> ALL SITES ACCESSIBLE WITHOUT PROXY FROM THIS RUNNER <<<")

    # flag any surprises: sites marked needs_proxy=True that actually worked fine
    surprises = [
        r for r in ok_no_proxy if r.get("known_needs_proxy") is True
    ]
    if surprises:
        print()
        print(">>> SURPRISE: these were marked needs_proxy=True but worked WITHOUT proxy:")
        for r in surprises:
            print(f"    - {r['brand']}")

    print()
    print("--- FULL JSON RESULTS ---")
    print(json.dumps(RESULTS, indent=2))

    with open("scrapling_akamai_test_results.json", "w") as f:
        json.dump(RESULTS, f, indent=2)


if __name__ == "__main__":
    main()
