import asyncio
import time
from dataclasses import dataclass
from queue import Empty, Queue
from typing import List, Optional

from inputs.base import SensorConfig
from inputs.base.loop import FuserInput
from providers.io_provider import IOProvider
from providers.http_locations_provider import HTTPLocationsProvider


@dataclass
class Message:
    timestamp: float
    message: str


class LocationsInput(FuserInput[str]):
    """Input plugin that publishes available saved locations for LLM prompts."""

    def __init__(self, config: SensorConfig = SensorConfig()):
        super().__init__(config)
        self.io_provider = IOProvider()
        self.provider = HTTPLocationsProvider(getattr(config, "list_endpoint", ""), getattr(config, "timeout", 5), getattr(config, "refresh_interval", 0))
        self.messages: List[Message] = []
        self.message_buffer: Queue[str] = Queue()
        self.descriptor_for_LLM = "Saved Locations"

        # If provider isn't running and has an endpoint but no refresh, try a one-off fetch
        if getattr(self.provider, "list_endpoint", None) and getattr(self.provider, "refresh_interval", 0) == 0:
            # schedule an immediate fetch in the background
            asyncio.get_event_loop().create_task(self._ensure_loaded())

    async def _ensure_loaded(self):
        # try to call provider._fetch_once if available
        func = getattr(self.provider, "_fetch_once", None)
        if callable(func):
            try:
                await func()
            except Exception:
                pass

    async def _poll(self) -> Optional[str]:
        await asyncio.sleep(0.5)
        locs = self.provider.get_all_locations()
        if not locs:
            return None
        # build a string
        lines = []
        for name, entry in locs.items():
            # friendly label
            label = entry.get("name") if isinstance(entry, dict) else name
            pose = entry.get("pose") if isinstance(entry, dict) else None
            if pose and isinstance(pose, dict):
                pos = pose.get("position", {})
                lines.append(f"{label} (x:{pos.get('x',0):.2f} y:{pos.get('y',0):.2f})")
            else:
                lines.append(f"{label}")
        return "\n".join(lines)

    async def _raw_to_text(self, raw_input: str) -> Message:
        return Message(timestamp=time.time(), message=raw_input)

    async def raw_to_text(self, raw_input: Optional[str]):
        if raw_input is None:
            return
        pending_message = await self._raw_to_text(raw_input)
        if pending_message is not None:
            self.messages.append(pending_message)

    def formatted_latest_buffer(self) -> Optional[str]:
        if len(self.messages) == 0:
            return None
        latest_message = self.messages[-1]
        result = (f"\nINPUT: {self.descriptor_for_LLM}\n// START\n" f"{latest_message.message}\n// END\n")
        self.io_provider.add_input(self.__class__.__name__, latest_message.message, latest_message.timestamp)
        self.messages = []
        return result
