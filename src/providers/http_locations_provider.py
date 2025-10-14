import asyncio
import json
import logging
from threading import Lock, Thread
from typing import Dict, Optional

import aiohttp

from .singleton import singleton


@singleton
class HTTPLocationsProvider:
    """Provider that fetches and caches a remote locations list.

    Usage:
      p = HTTPLocationsProvider(list_endpoint=url)
      p.get_location('kitchen') -> dict or None
    """

    def __init__(self, list_endpoint: str = "", timeout: int = 5, refresh_interval: int = 0):
        self.list_endpoint = list_endpoint
        self.timeout = timeout
        self.refresh_interval = refresh_interval
        self._lock = Lock()
        self._locations: Dict[str, Dict] = {}
        self.running = False

        if self.list_endpoint and self.refresh_interval > 0:
            self.start()

    def start(self):
        if self.running:
            return
        self.running = True
        t = Thread(target=self._background_loop, daemon=True)
        t.start()

    def stop(self):
        self.running = False

    def _background_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while self.running:
            try:
                loop.run_until_complete(self._fetch_once())
            except Exception:
                logging.exception("Error refreshing locations")
            finally:
                loop.run_until_complete(asyncio.sleep(self.refresh_interval))

    async def _fetch_once(self):
        if not self.list_endpoint:
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.list_endpoint, timeout=self.timeout) as resp:
                    text = await resp.text()
                    if resp.status < 200 or resp.status >= 300:
                        logging.error(f"Location list API returned {resp.status}: {text}")
                        return
                    data = json.loads(text)
                    raw_message = data.get("message") if isinstance(data, dict) else None
                    if raw_message and isinstance(raw_message, str):
                        try:
                            locations = json.loads(raw_message)
                        except Exception:
                            logging.error("Failed to parse nested message JSON from location list")
                            return
                    elif isinstance(data, dict) and "message" not in data:
                        locations = data
                    else:
                        logging.error("Unexpected format from location list API")
                        return
                    self._update_locations(locations)
        except asyncio.TimeoutError:
            logging.error("HTTP request to location list timed out")
        except Exception:
            logging.exception("Error querying location list")

    def _update_locations(self, locations_raw):
        parsed = {}
        if isinstance(locations_raw, dict):
            for k, v in locations_raw.items():
                name = k
                entry = v if isinstance(v, dict) else {"name": k, "pose": {}}
                entry.setdefault("name", k)
                parsed[name.strip().lower()] = entry
        elif isinstance(locations_raw, list):
            for item in locations_raw:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or item.get("label") or "").strip()
                if not name:
                    continue
                parsed[name.lower()] = item

        with self._lock:
            self._locations = parsed
        logging.info(f"HTTPLocationsProvider loaded {len(parsed)} locations")

    def get_all_locations(self) -> Dict[str, Dict]:
        with self._lock:
            return dict(self._locations)

    def get_location(self, label: str) -> Optional[Dict]:
        if not label:
            return None
        key = label.strip().lower()
        with self._lock:
            return self._locations.get(key)
