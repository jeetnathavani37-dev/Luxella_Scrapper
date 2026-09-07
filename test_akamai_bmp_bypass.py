"""
test_akamai_bmp_bypass.py

EXPERIMENT: does injecting Akamai mobile-app-SDK sensor data (from the vendored
akamai_bmp/ Go server) into a plain `requests` call help bypass Akamai Bot Manager
on the WEBSITES in sites.py?

Expected result: NO. Website Akamai Bot Manager validates JS-generated browser
sensor data (bm-sz/_abck cookie flow); this tool generates the unrelated mobile-app
SDK sensor data format. This script exists to make that gap concrete/testable rather
than assumed - see akamai_bmp/README.md for the full explanation.

Usage:
    cd akamai_bmp && go build -o /tmp/akamai-bmp-server ./cmd/akamai-bmp-server && cd ..
    python test_akamai_bmp_bypass.py
"""

import json
import os
import time

import requests

from akamai_bmp_client import AkamaiBmpClient, AkamaiBmpServerProcess
from sites import SITES

BMP_BINARY = os.environ.get("AKAMAI_BMP_BINARY", "/tmp/akamai-bmp-server")
DEVICES_PATH = os.environ.get("AKAMAI_BMP_DEVICES", "akamai_bmp/db/devices.json")

# A handful of the sites.py entries the repo notes have historically been
# hard-blocked (see sites.py NOTE 2026-08-29 re: MK/Coach).
TARGET_NAMES = {"michaelkors", "coach", "toryburch", "ralphlauren"}


def build_targets():
    targets = []
    for site in SITES:
        if site["name"] not in TARGET_NAMES:
            continue
        url = site["start_urls"][0] if "start_urls" in site else site.get("domain")
        if url:
            targets.append({"brand": site["name"], "url": url})
    return targets


def looks_blocked(resp):
    return resp.status_code in (403, 429, 999) or len(resp.content) < 5000


def fetch(url, headers=None):
    t0 = time.time()
    try:
        resp = requests.get(url, headers=headers or {}, timeout=20)
        return {
            "status": resp.status_code,
            "body_length": len(resp.content),
            "looks_blocked": looks_blocked(resp),
            "time_s": round(time.time() - t0, 2),
        }
    except requests.RequestException as e:
        return {"status": "EXCEPTION", "error": str(e), "time_s": round(time.time() - t0, 2)}


def main():
    client = AkamaiBmpClient()
    server_proc = None
    if not client.is_up():
        print(f"BMP server not reachable at {client.base_url}, starting {BMP_BINARY} ...")
        server_proc = AkamaiBmpServerProcess(BMP_BINARY, devices_path=DEVICES_PATH).start()
        if not client.is_up():
            print("Could not start BMP server. Build it first:")
            print("  cd akamai_bmp && go build -o /tmp/akamai-bmp-server ./cmd/akamai-bmp-server")
            return

    results = []
    try:
        for target in build_targets():
            print(f"\n=== {target['brand']} ({target['url']}) ===")

            baseline = fetch(target["url"])
            print(f"  baseline (no sensor):  {baseline}")

            try:
                bmp = client.generate(app="com.example.app", version="3.3.4")
                headers = {
                    "X-acf-sensor-data": bmp["sensor"],
                    "User-Agent": f"Mozilla/5.0 (Linux; Android {bmp['androidVersion']}; {bmp['model']})",
                }
                with_sensor = fetch(target["url"], headers=headers)
            except Exception as e:
                with_sensor = {"status": "EXCEPTION", "error": str(e)}
            print(f"  with mobile sensor:    {with_sensor}")

            results.append({
                "brand": target["brand"],
                "url": target["url"],
                "baseline": baseline,
                "with_mobile_sensor": with_sensor,
                "sensor_changed_outcome": (
                    baseline.get("looks_blocked") != with_sensor.get("looks_blocked")
                    if "looks_blocked" in baseline and "looks_blocked" in with_sensor
                    else None
                ),
            })
    finally:
        if server_proc:
            server_proc.stop()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    changed = [r for r in results if r["sensor_changed_outcome"]]
    print(f"Sites tested: {len(results)}")
    print(f"Sites where the mobile sensor header changed the block outcome: {len(changed)}")
    if not changed:
        print("As expected: mobile-app SDK sensor data has no effect on website Akamai.")

    with open("akamai_bmp_test_results.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
