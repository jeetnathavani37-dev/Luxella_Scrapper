# Akamai BMP Generator (vendored, experimental)

Vendored from [xvertile/akamai-bmp-generator](https://github.com/xvertile/akamai-bmp-generator)
(original creator: [ui0x](https://github.com/ui0x)). Go server that generates
Akamai Bot Manager **mobile-app SDK** sensor data (`sensor_data` payload sent by
native Android/iOS apps to their backend APIs).

## Read this before using it

**This does NOT generate the sensor data used by Akamai on regular desktop/mobile
websites.** Website Akamai Bot Manager runs JavaScript in the browser (mouse/keyboard
events, canvas fingerprinting, etc.) and produces a `bm-sz` / `_abck` cookie flow that is
a completely different protocol from the Android/iOS SDK format this tool reverses.

This tool is only useful if a specific brand's *mobile app* talks to a backend API that
is itself protected by Akamai's mobile SDK (you'd need to know the app's package id,
e.g. `com.kohls.mcommerce.opal`, and the actual API endpoint the app calls — not the
public website URL). It was vendored here as an experiment per request; it is **not**
wired into `main.py` / `sites.py` and does not change how any site in this scraper is
currently fetched.

## What's included / changed vs upstream

- `cmd/akamai-bmp-server/main.go` uses the **older, working** version map (`2.1.2` →
  `4.2.1`, 9 versions). Upstream's newer `cmd/akamai-bmp-server/main.go` also wires up
  `3.3.9` and `4.0.2`, but those two packages (`bm/3.3.9`, `bm/4.0.2`) call SDK helpers
  (`sdk.RandomHex`, `sdk.SystemInfo`, `sdk.EventListeners`, `bm.encryptSensor`, ...) that
  don't exist in `sdk/sdk.go` / `bm/bm.go` as of the commit vendored here — they don't
  compile. Swapped in the version map that only references working generators.
- `db/devices.json` trimmed from ~2056 to 250 device fingerprints to keep this repo
  light (~5MB instead of ~83MB). Swap in the full file with `-devicepath` if you need
  more variety.

## Run it

```bash
cd akamai_bmp
go build -o /tmp/akamai-bmp-server ./cmd/akamai-bmp-server
/tmp/akamai-bmp-server --host 127.0.0.1 --port 1337 --devicepath db/devices.json
```

Or with Docker:

```bash
cd akamai_bmp
docker build -t akamai-bmp-server .
docker run -p 1337:1337 akamai-bmp-server
```

## API

```
POST /akamai/bmp
{
  "app": "com.example.app",
  "lang": "en_US",
  "version": "3.3.4",
  "challenge": false,
  "powUrl": ""
}
```

Supported `version` values: `4.2.1`, `3.3.4`, `3.3.1`, `3.3.0`, `3.2.3`, `3.1.0`,
`2.2.3`, `2.2.2`, `2.1.2`.

Response:

```json
{
  "sensor": "3,a,...",
  "androidVersion": "9",
  "model": "SM-G950F",
  "brand": "samsung",
  "screenSize": "1080x1920"
}
```

## Python client

See `../akamai_bmp_client.py` for a thin Python wrapper, and
`../test_akamai_bmp_bypass.py` for an experiment script that tries feeding generated
sensor data into a request against a target URL and checks whether it changes the
block/no-block outcome (see caveat above — expected result against a normal e-commerce
website is "no effect").
