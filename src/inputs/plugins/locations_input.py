import asyncio
import logging
import time
from dataclasses import dataclass
from typing import List, Optional

from inputs.base import SensorConfig
from inputs.base.loop import FuserInput
from providers.io_provider import IOProvider


@dataclass
class Message:
    timestamp: float
    message: str


class LocationsInput(FuserInput[str]):
    """
    Input plugin that publishes available saved locations for LLM prompts.
    
    Reads locations from IOProvider (populated by Locations background task).
    """

    def __init__(self, config: SensorConfig = SensorConfig()):
        super().__init__(config)
        self.io_provider = IOProvider()
        self.messages: List[Message] = []
        self.descriptor_for_LLM = "These are the saved locations you can navigate to."

    async def _poll(self) -> Optional[str]:
        """Poll IOProvider for locations data."""
        await asyncio.sleep(0.5)
        
        # Get locations from IOProvider (populated by background task)
        locs = self.io_provider.get_dynamic_variable("available_locations")
        logging.debug(f"LocationsInput._poll: got locations from IOProvider: {locs}")
        
        if not locs or not isinstance(locs, dict):
            logging.debug(f"LocationsInput._poll: no locations available (type: {type(locs)})")
            return None
        
        # Build a string for LLM
        lines = []
        for name, entry in locs.items():
            label = entry.get("name") if isinstance(entry, dict) else name
            pose = entry.get("pose") if isinstance(entry, dict) else None
            if pose and isinstance(pose, dict):
                pos = pose.get("position", {})
                lines.append(f"{label} (x:{pos.get('x',0):.2f} y:{pos.get('y',0):.2f})")
            else:
                lines.append(f"{label}")
        
        result = "\n".join(lines)
        logging.info(f"LocationsInput: formatted {len(lines)} locations")
        return result

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
        result = (
            f"\nINPUT: {self.descriptor_for_LLM}\n// START\n"
            f"{latest_message.message}\n// END\n"
        )
        self.io_provider.add_input(
            self.__class__.__name__, 
            latest_message.message, 
            latest_message.timestamp
        )
        self.messages = []
        return result
