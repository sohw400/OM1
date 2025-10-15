import asyncio
import json
import logging
import threading
from typing import Dict, Optional

import aiohttp

from .io_provider import IOProvider
from .singleton import singleton


@singleton
class LocationsProvider:
    """
    Provider that fetches locations from HTTP API in a background thread.

    Follows the same pattern as GpsProvider, OdomProvider, etc.

    Usage:
      p = LocationsProvider(list_endpoint=url, refresh_interval=30)
      p.start()  # Starts background thread
      loc = p.get_location('kitchen')
    """

    def __init__(
        self, list_endpoint: str = "", timeout: int = 5, refresh_interval: int = 30
    ):
        """
        Initialize the provider.

        Parameters:
          list_endpoint: URL to fetch locations from
          timeout: HTTP request timeout in seconds
          refresh_interval: How often to fetch (seconds)
        """
        self.list_endpoint = list_endpoint
        self.timeout = timeout
        self.refresh_interval = refresh_interval
        self._locations: Dict[str, Dict] = {}
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Get IOProvider to store locations for inputs to access
        try:
            self.io_provider = IOProvider()
        except Exception:
            logging.exception("Failed to get IOProvider in LocationsProvider")
            self.io_provider = None

    def start(self) -> None:
        """Start the background fetch thread."""
        if self._running:
            logging.warning("LocationsProvider already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logging.info("LocationsProvider background thread started")

    def stop(self) -> None:
        """Stop the background fetch thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        """Background thread that periodically fetches locations."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while self._running:
            try:
                loop.run_until_complete(self._fetch())
            except Exception:
                logging.exception("Error fetching locations")

            # Sleep in small increments so we can stop quickly
            for _ in range(self.refresh_interval):
                if not self._running:
                    break
                asyncio.run(asyncio.sleep(1))

    async def _fetch(self) -> None:
        """Fetch locations from the API and update cache."""
        if not self.list_endpoint:
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.list_endpoint, timeout=self.timeout
                ) as resp:
                    text = await resp.text()
                    if resp.status < 200 or resp.status >= 300:
                        logging.error(
                            f"Location list API returned {resp.status}: {text}"
                        )
                        return

                    data = json.loads(text)

                    # Handle nested message format
                    raw_message = (
                        data.get("message") if isinstance(data, dict) else None
                    )
                    if raw_message and isinstance(raw_message, str):
                        try:
                            locations = json.loads(raw_message)
                        except Exception:
                            logging.error(
                                "Failed to parse nested message JSON from location list"
                            )
                            return
                    elif isinstance(data, dict) and "message" not in data:
                        locations = data
                    else:
                        logging.error("Unexpected format from location list API")
                        return

                    self._update_locations(locations)

        except Exception:
            logging.exception("Error fetching locations")

    def _update_locations(self, locations_raw) -> None:
        """Parse and store locations."""
        parsed = {}

        if isinstance(locations_raw, dict):
            for k, v in locations_raw.items():
                entry = v if isinstance(v, dict) else {"name": k, "pose": {}}
                entry.setdefault("name", k)
                parsed[k.strip().lower()] = entry

        elif isinstance(locations_raw, list):
            for item in locations_raw:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or item.get("label") or "").strip()
                if not name:
                    continue
                parsed[name.lower()] = item

        self._locations = parsed

        # Store in IOProvider so LocationsInput can access it
        if self.io_provider is not None:
            self.io_provider.add_dynamic_variable("available_locations", parsed)
            logging.info(
                f"LocationsProvider loaded {len(parsed)} locations and stored in IOProvider"
            )
        else:
            logging.info(f"LocationsProvider loaded {len(parsed)} locations")

    def get_all_locations(self) -> Dict[str, Dict]:
        """Get all cached locations."""
        return dict(self._locations)

    def get_location(self, label: str) -> Optional[Dict]:
        """Get a specific location by label."""
        if not label:
            return None
        key = label.strip().lower()
        return self._locations.get(key)
