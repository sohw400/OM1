import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

from inputs.base import SensorConfig
from inputs.base.loop import FuserInput
from providers.bh1750_provider import BH1750Provider
from providers.io_provider import IOProvider


@dataclass
class Message:
    """
    Container for timestamped light sensor readings.

    Parameters
    ----------
    timestamp : float
        Unix timestamp when the measurement was taken
    message : str
        Human-readable description of the light level
    """

    timestamp: float
    message: str


class BH1750Light(FuserInput[dict]):
    """
    BH1750 ambient light sensor input.

    Monitors illuminance levels using a BH1750 digital light sensor
    and provides natural language descriptions of lighting conditions.
    Useful for robots that need to adapt behavior based on ambient light,
    such as adjusting camera settings or navigation strategies.
    """

    def __init__(self, config: SensorConfig = SensorConfig()):
        """
        Initialize the BH1750 light sensor input.

        Configuration parameters:
        - address: I2C address of the sensor (default: 0x23)
        - bus: I2C bus number (default: 1)
        - mock_mode: Use simulated data for testing (default: False)
        """
        super().__init__(config)

        self.io_provider = IOProvider()
        self.messages: list[Message] = []

        address = getattr(config, "address", 0x23)
        bus = getattr(config, "bus", 1)
        mock_mode = getattr(config, "mock_mode", False)

        self.bh1750 = BH1750Provider(address=address, bus=bus, mock_mode=mock_mode)
        self.descriptor_for_LLM = "Ambient Light"

    async def _poll(self) -> Optional[dict]:
        """
        Poll the sensor for new light readings.

        Returns
        -------
        Optional[dict]
            Current light level data or None if unavailable
        """
        await asyncio.sleep(0.5)

        try:
            return self.bh1750.data
        except Exception as e:
            logging.debug(f"Error polling BH1750 sensor: {e}")
            return None

    async def _raw_to_text(self, raw_input: dict) -> Optional[Message]:
        """
        Convert raw sensor data into descriptive text.

        Parameters
        ----------
        raw_input : dict
            Dictionary containing lux value and condition

        Returns
        -------
        Optional[Message]
            Formatted message describing the lighting situation
        """
        if not raw_input:
            return None

        try:
            lux = raw_input["lux"]
            condition = raw_input["condition"]
            timestamp = raw_input["timestamp"]

            # Build a natural description
            msg_parts = [f"The ambient light level is {lux:.0f} lux"]

            # Add contextual information based on the lighting level
            if condition == "dark":
                msg_parts.append(
                    "It's quite dark here. Visibility is limited and artificial lighting would be helpful."
                )
            elif condition == "dim":
                msg_parts.append(
                    "Lighting is dim, similar to a room with minimal lighting or twilight conditions."
                )
            elif condition == "moderate":
                msg_parts.append(
                    "The lighting is comfortable for most activities, typical of well-lit indoor spaces."
                )
            elif condition == "bright":
                msg_parts.append(
                    "It's bright, comparable to an office or outdoor shade on a sunny day."
                )
            else:
                msg_parts.append(
                    "Very bright conditions, similar to direct sunlight or intense artificial lighting."
                )

            msg = " ".join(msg_parts)
            return Message(timestamp=timestamp, message=msg)

        except KeyError as e:
            logging.error(f"Missing expected data in sensor reading: {e}")
            return None

    async def raw_to_text(self, raw_input: Optional[dict]):
        """
        Process sensor input and add to message buffer.

        Parameters
        ----------
        raw_input : Optional[dict]
            Raw sensor data to process
        """
        if raw_input is None:
            return

        pending_message = await self._raw_to_text(raw_input)

        if pending_message is not None:
            self.messages.append(pending_message)

    def formatted_latest_buffer(self) -> Optional[str]:
        """
        Get the most recent light reading as formatted text.

        Returns
        -------
        Optional[str]
            Formatted description of current lighting conditions
        """
        if len(self.messages) == 0:
            return None

        latest_message = self.messages[-1]

        result = (
            f"\nINPUT: {self.descriptor_for_LLM}\n// START\n"
            f"{latest_message.message}\n// END\n"
        )

        self.io_provider.add_input(
            self.__class__.__name__, latest_message.message, latest_message.timestamp
        )
        self.messages = []

        return result
