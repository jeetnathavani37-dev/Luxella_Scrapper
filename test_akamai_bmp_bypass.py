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
            print(f"  1. baseline (default python-requests UA, no sensor):  {baseline}")

            try:
                bmp = client.generate(app="com.example.app", version="3.3.4")
                android_ua = f"Mozilla/5.0 (Linux; Android {bmp['androidVersion']}; {bmp['model']})"
            except Exception as e:
                bmp = None
                android_ua = None
                print(f"  BMP generate() failed: {e}")

            # Control: same Android User-Agent, but WITHOUT the sensor header.
            # Isolates whether a bypass is caused by the sensor data itself or
            # just by no longer using the dead-giveaway python-requests UA.
            if android_ua:
                ua_only = fetch(target["url"], headers={"User-Agent": android_ua})
            else:
                ua_only = {"status": "SKIPPED"}
            print(f"  2. Android UA only, no sensor header:                 {ua_only}")

            if bmp:
                headers = {
                    "X-acf-sensor-data": bmp["sensor"],
                    "User-Agent": android_ua,
                }
                with_sensor = fetch(target["url"], headers=headers)
            else:
                with_sensor = {"status": "SKIPPED"}
            print(f"  3. Android UA + X-acf-sensor-data (mobile sensor):    {with_sensor}")

            def changed(a, b):
                return (
                    a.get("looks_blocked") != b.get("looks_blocked")
                    if "looks_blocked" in a and "looks_blocked" in b
                    else None
                )

            results.append({
                "brand": target["brand"],
                "url": target["url"],
                "baseline": baseline,
                "ua_only_no_sensor": ua_only,
                "with_mobile_sensor": with_sensor,
                "ua_alone_changed_outcome": changed(baseline, ua_only),
                "sensor_changed_outcome_vs_ua_only": changed(ua_only, with_sensor),
            })
    finally:
        if server_proc:
            server_proc.stop()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    ua_flips = [r for r in results if r["ua_alone_changed_outcome"]]
    sensor_flips = [r for r in results if r["sensor_changed_outcome_vs_ua_only"]]
    print(f"Sites tested: {len(results)}")
    print(f"Sites where swapping to an Android UA alone (no sensor) changed the outcome: {len(ua_flips)}")
    print(f"Sites where ADDING the sensor header on top of that UA changed the outcome further: {len(sensor_flips)}")
    if ua_flips and not sensor_flips:
        print("=> The bypass is coming from the User-Agent change, NOT the mobile sensor data.")
    elif sensor_flips:
        print("=> The sensor header changed outcomes beyond the UA alone - worth digging into further.")

    with open("akamai_bmp_test_results.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
