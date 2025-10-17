import logging
import threading
import time
from typing import Optional

from .singleton import singleton


@singleton
class BH1750Provider:
    """
    Provider for BH1750 ambient light sensor.

    The BH1750 is an I2C digital light sensor that measures illuminance
    in lux. This provider supports both actual hardware communication and
    a mock mode for testing purposes.

    Parameters
    ----------
    address : int
        I2C address of the sensor (default: 0x23)
    bus : int
        I2C bus number (default: 1)
    mock_mode : bool
        Enable simulation mode for testing without hardware
    """

    def __init__(self, address: int = 0x23, bus: int = 1, mock_mode: bool = False):
        """
        Initialize the BH1750 light sensor provider.
        """
        self.address = address
        self.bus = bus
        self.mock_mode = mock_mode
        self.running = False
        self._thread: Optional[threading.Thread] = None

        self.lux: float = 0.0
        self.last_read_time: float = 0.0
        self._data: Optional[dict] = None

        # Attempt to initialize the sensor hardware
        self.sensor = None
        if not mock_mode:
            try:
                import smbus2

                self.smbus = smbus2.SMBus(bus)
                # Send power on command
                self.smbus.write_byte(self.address, 0x01)
                time.sleep(0.01)
                # Set to continuous high resolution mode
                self.smbus.write_byte(self.address, 0x10)
                self.sensor = True
                logging.info(
                    f"BH1750 sensor initialized at address 0x{address:02x} on bus {bus}"
                )
            except ImportError:
                logging.warning(
                    "smbus2 library not available, switching to mock mode"
                )
                self.mock_mode = True
            except Exception as e:
                logging.warning(f"Could not initialize BH1750 sensor: {e}")
                self.mock_mode = True

        if self.mock_mode:
            logging.info("BH1750 provider running in mock mode")

        self.start()

    def _read_light_level(self):
        """
        Read the current light level from the sensor.
        """
        if self.mock_mode:
            import random

            # Simulate realistic indoor lighting variations
            base_lux = 250.0
            variation = random.uniform(-50.0, 100.0)
            self.lux = max(0, base_lux + variation)
        else:
            try:
                if self.sensor:
                    # Read two bytes from the sensor
                    data = self.smbus.read_i2c_block_data(self.address, 0x10, 2)
                    # Convert to lux value
                    raw_value = (data[0] << 8) | data[1]
                    self.lux = round(raw_value / 1.2, 1)
            except Exception as e:
                logging.debug(f"Error reading BH1750 sensor: {e}")

        self.last_read_time = time.time()
        self._update_data()

    def _update_data(self):
        """
        Update the internal data structure with current readings.
        """
        # Determine lighting conditions for context
        if self.lux < 10:
            condition = "dark"
        elif self.lux < 100:
            condition = "dim"
        elif self.lux < 500:
            condition = "moderate"
        elif self.lux < 1000:
            condition = "bright"
        else:
            condition = "very bright"

        self._data = {
            "lux": self.lux,
            "condition": condition,
            "timestamp": self.last_read_time,
        }

    def start(self):
        """
        Start the sensor reading thread.
        """
        if self._thread and self._thread.is_alive():
            return

        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logging.info("BH1750 provider started")

    def _run(self):
        """
        Main reading loop. The BH1750 can be read fairly frequently,
        but we use a reasonable interval to avoid unnecessary overhead.
        """
        while self.running:
            self._read_light_level()
            time.sleep(1.0)

    def stop(self):
        """
        Stop the sensor provider and clean up resources.
        """
        self.running = False
        if self._thread:
            logging.info("Stopping BH1750 provider")
            self._thread.join(timeout=5)

        if self.sensor and not self.mock_mode:
            try:
                # Send power down command
                self.smbus.write_byte(self.address, 0x00)
                self.smbus.close()
            except Exception as e:
                logging.debug(f"Error during BH1750 cleanup: {e}")

    @property
    def data(self) -> Optional[dict]:
        """
        Get the current sensor data.

        Returns
        -------
        Optional[dict]
            Dictionary containing lux value and lighting condition,
            or None if no data is available
        """
        return self._data
