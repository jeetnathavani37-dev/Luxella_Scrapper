"""
akamai_bmp_client.py

Thin Python client for the vendored Akamai BMP Generator Go server
(akamai_bmp/). Generates Akamai Bot Manager MOBILE-APP SDK sensor data.

IMPORTANT: this is the mobile-app protocol, not the JS-based sensor data
used by Akamai Bot Manager on regular websites. See akamai_bmp/README.md.
Requires the Go server to be running separately:

    cd akamai_bmp
    go build -o /tmp/akamai-bmp-server ./cmd/akamai-bmp-server
    /tmp/akamai-bmp-server --host 127.0.0.1 --port 1337 --devicepath db/devices.json
"""

import subprocess
import time

import requests

SUPPORTED_VERSIONS = [
    "4.2.1", "3.3.4", "3.3.1", "3.3.0",
    "3.2.3", "3.1.0", "2.2.3", "2.2.2", "2.1.2",
]


class AkamaiBmpClient:
    def __init__(self, base_url="http://127.0.0.1:1337", timeout=20):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(self, app, lang="en_US", version="3.3.4", challenge=False, pow_url=""):
        """Request a sensor_data payload from the BMP server.

        Returns a dict: {sensor, androidVersion, model, brand, screenSize}.
        Raises requests.HTTPError on non-200 responses.
        """
        if version not in SUPPORTED_VERSIONS:
            raise ValueError(f"Unsupported BMP version {version!r}, expected one of {SUPPORTED_VERSIONS}")

        resp = requests.post(
            f"{self.base_url}/akamai/bmp",
            json={
                "app": app,
                "lang": lang,
                "version": version,
                "challenge": challenge,
                "powUrl": pow_url,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def is_up(self):
        try:
            requests.post(f"{self.base_url}/akamai/bmp", json={}, timeout=3)
            return True
        except requests.exceptions.ConnectionError:
            return False
        except requests.exceptions.RequestException:
            return True  # server responded (likely 400 on empty body) -> it's up


class AkamaiBmpServerProcess:
    """Launches/stops the vendored Go server as a subprocess for local experiments."""

    def __init__(self, binary_path, devices_path="akamai_bmp/db/devices.json",
                 host="127.0.0.1", port=1337):
        self.binary_path = binary_path
        self.devices_path = devices_path
        self.host = host
        self.port = port
        self.proc = None

    def start(self, wait_seconds=1.5):
        self.proc = subprocess.Popen(
            [self.binary_path, "--host", self.host, "--port", str(self.port),
             "--devicepath", self.devices_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        time.sleep(wait_seconds)
        return self

    def stop(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
