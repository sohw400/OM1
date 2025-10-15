import asyncio
import logging
from typing import Any

import aiohttp

from actions.base import ActionConfig, ActionConnector
from actions.remember_location.interface import RememberLocationInput


class RememberLocationConnector(ActionConnector[RememberLocationInput]):
    """
    Connector that persists a remembered location by POSTing to an HTTP API.

    Configuration options (in action config):
      - endpoint: URL to POST to (required)
      - api_key: optional API key to include in Authorization header
      - timeout: request timeout in seconds (default 5)
    """

    def __init__(self, config: ActionConfig):
        super().__init__(config)
        self.endpoint = getattr(config, "endpoint", None)
        self.api_key = getattr(config, "api_key", None)
        self.timeout = getattr(config, "timeout", 5)
        self.map_name = getattr(config, "map_name", "map")

    async def connect(self, input_protocol: RememberLocationInput) -> None:
        if not self.endpoint:
            logging.error("RememberLocation connector missing 'endpoint' in config")
            return

        payload: dict[str, Any] = {
            "map_name": self.map_name,
            "label": input_protocol.action,
            "description": getattr(input_protocol, "description", ""),
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.endpoint, json=payload, headers=headers, timeout=self.timeout
                ) as resp:
                    text = await resp.text()
                    if resp.status >= 200 and resp.status < 300:
                        logging.info(
                            f"RememberLocation: stored '{input_protocol.action}' -> {resp.status} {text}"
                        )
                    else:
                        logging.error(
                            f"RememberLocation API returned {resp.status}: {text}"
                        )
        except asyncio.TimeoutError:
            logging.error("RememberLocation API request timed out")
        except Exception as e:
            logging.error(f"RememberLocation API request failed: {e}")
