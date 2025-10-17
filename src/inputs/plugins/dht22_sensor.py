import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

from inputs.base import SensorConfig
from inputs.base.loop import FuserInput
from providers.dht22_provider import DHT22Provider
from providers.io_provider import IOProvider


@dataclass
class Message:
    """
    Container for timestamped sensor messages.

    Parameters
    ----------
    timestamp : float
        Unix timestamp of the measurement
    message : str
        Formatted message describing the sensor readings
    """

    timestamp: float
    message: str


class DHT22Sensor(FuserInput[dict]):
    """
    DHT22 temperature and humidity sensor input.

    Reads environmental data from a DHT22 sensor and formats it
    for processing by the OM1 agent system. Supports both hardware
    and mock modes for development and testing.
    """

    def __init__(self, config: SensorConfig = SensorConfig()):
        """
        Initialize DHT22 sensor input.

        Configuration options:
        - pin: GPIO pin number (default: 4)
        - mock_mode: Use simulated data (default: False)
        """
        super().__init__(config)

        self.io_provider = IOProvider()
        self.messages: list[Message] = []

        pin = getattr(config, "pin", 4)
        mock_mode = getattr(config, "mock_mode", False)

        self.dht22 = DHT22Provider(pin=pin, mock_mode=mock_mode)
        self.descriptor_for_LLM = "Environment Sensor"

    async def _poll(self) -> Optional[dict]:
        """
        Poll for new sensor readings.

        Retrieves the latest temperature and humidity data
        from the DHT22 provider.

        Returns
        -------
        Optional[dict]
            Sensor data dictionary or None if unavailable
        """
        await asyncio.sleep(0.5)

        try:
            return self.dht22.data
        except Exception as e:
            logging.debug(f"Error polling DHT22: {e}")
            return None

    async def _raw_to_text(self, raw_input: dict) -> Optional[Message]:
        """
        Convert sensor data to human-readable text.

        Parameters
        ----------
        raw_input : dict
            Raw sensor data containing temperature and humidity

        Returns
        -------
        Optional[Message]
            Formatted message with sensor readings
        """
        if not raw_input:
            return None

        try:
            temp_c = raw_input["temperature_celsius"]
            temp_f = raw_input["temperature_fahrenheit"]
            humidity = raw_input["humidity_percent"]
            timestamp = raw_input["timestamp"]

            # Interpret comfort level
            comfort = ""
            if humidity < 30:
                comfort = "The air feels quite dry."
            elif humidity > 70:
                comfort = "The air feels humid."

            if temp_c < 18:
                temp_feel = "cool"
            elif temp_c > 26:
                temp_feel = "warm"
            else:
                temp_feel = "comfortable"

            msg = (
                f"Current temperature is {temp_c:.1f}°C ({temp_f:.1f}°F), "
                f"which feels {temp_feel}. Humidity is at {humidity:.1f}%. "
                f"{comfort}".strip()
            )

            return Message(timestamp=timestamp, message=msg)
        except KeyError as e:
            logging.error(f"Missing key in sensor data: {e}")
            return None

    async def raw_to_text(self, raw_input: Optional[dict]):
        """
        Process raw sensor input and update message buffer.

        Parameters
        ----------
        raw_input : Optional[dict]
            Sensor data to process
        """
        if raw_input is None:
            return

        pending_message = await self._raw_to_text(raw_input)

        if pending_message is not None:
            self.messages.append(pending_message)

    def formatted_latest_buffer(self) -> Optional[str]:
        """
        Format and return the latest sensor reading.

        Retrieves the most recent measurement, formats it for display,
        logs it to the IO provider, and clears the message buffer.

        Returns
        -------
        Optional[str]
            Formatted sensor reading or None if buffer is empty
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
