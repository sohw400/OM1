import asyncio
import json
import logging
import threading
from typing import Dict, List, Optional, Union

import aiohttp

from .io_provider import IOProvider
from .singleton import singleton


@singleton
class LocationsProvider:
    """
    Provider that fetches locations from HTTP API in a background thread.
    """

    def __init__(
        self,
        location_endpoint: str = "http://localhost:5000/maps/locations/list",
        timeout: int = 5,
        refresh_interval: int = 30,
    ):
        """
        Initialize the provider.

        Parameters
        ----------
        location_endpoint : str
            The HTTP endpoint to fetch locations from. Default is "http://localhost:5000/maps/locations/list".
        timeout : int
            Timeout for HTTP requests in seconds.
        refresh_interval : int
            How often to refresh locations in seconds.
        """
        self.location_endpoint = location_endpoint
        self.timeout = timeout
        self.refresh_interval = refresh_interval
        self._locations: Dict[str, Dict] = {}
        self._thread: Optional[threading.Thread] = None
        self._running = False

        self.io_provider = IOProvider()

    def start(self) -> None:
        """
        Start the background fetch thread.
        """
        if self._running:
            logging.warning("LocationsProvider already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logging.info("LocationsProvider background thread started")

    def stop(self) -> None:
        """
        Stop the background fetch thread.
        """
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        """
        Background thread that periodically fetches locations.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while self._running:
            try:
                loop.run_until_complete(self._fetch())
            except Exception:
                logging.exception("Error fetching locations")

            for _ in range(self.refresh_interval):
                if not self._running:
                    break
                asyncio.run(asyncio.sleep(1))

    async def _fetch(self) -> None:
        """
        Fetch locations from the API and update cache.
        """
        if not self.location_endpoint:
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.location_endpoint, timeout=self.timeout
                ) as resp:
                    text = await resp.text()
                    if resp.status < 200 or resp.status >= 300:
                        logging.error(
                            f"Location list API returned {resp.status}: {text}"
                        )
                        return

                    data = json.loads(text)

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

    def _update_locations(self, locations_raw: Union[Dict, List]) -> None:
        """
        Parse and store locations.

        Parameters
        ----------
        locations_raw : Dict or List
            Raw locations data from the API.
        """
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

    def get_all_locations(self) -> Dict[str, Dict]:
        """
        Get all cached locations.

        Returns
        -------
        Dict
            A dictionary of all locations keyed by their labels.
        """
        return dict(self._locations)

    def get_location(self, label: str) -> Optional[Dict]:
        """
        Get a specific location by label.

        Parameters
        ----------
        label : str
            The label of the location to retrieve.

        Returns
        -------
        Dict or None
            The location data if found, otherwise None.
        """
        if not label:
            return None
        key = label.strip().lower()
        return self._locations.get(key)
