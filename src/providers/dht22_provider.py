import logging
import threading
import time
from typing import Optional

from .singleton import singleton


@singleton
class DHT22Provider:
    """
    DHT22 sensor provider for temperature and humidity readings.

    Supports both hardware and mock modes. In hardware mode, reads from
    a DHT22 sensor via GPIO. In mock mode, generates simulated readings
    for testing without physical hardware.

    Parameters
    ----------
    pin : int
        GPIO pin number where DHT22 data line is connected
    mock_mode : bool
        If True, generates simulated data instead of reading from hardware
    """

    def __init__(self, pin: int = 4, mock_mode: bool = False):
        """
        Initialize DHT22 sensor provider.
        """
        self.pin = pin
        self.mock_mode = mock_mode
        self.running = False
        self._thread: Optional[threading.Thread] = None

        self.temperature_celsius: float = 0.0
        self.humidity_percent: float = 0.0
        self.last_read_time: float = 0.0
        self._data: Optional[dict] = None

        # Try importing Adafruit library if not in mock mode
        self.sensor = None
        if not mock_mode:
            try:
                import adafruit_dht
                import board

                # Map pin number to board pin
                pin_map = {
                    4: board.D4,
                    17: board.D17,
                    18: board.D18,
                    27: board.D27,
                    22: board.D22,
                    23: board.D23,
                    24: board.D24,
                    25: board.D25,
                }

                board_pin = pin_map.get(pin, board.D4)
                self.sensor = adafruit_dht.DHT22(board_pin)
                logging.info(f"DHT22 initialized on GPIO pin {pin}")
            except ImportError:
                logging.warning(
                    "adafruit_dht library not found, falling back to mock mode"
                )
                self.mock_mode = True
            except Exception as e:
                logging.warning(f"Failed to initialize DHT22 sensor: {e}")
                self.mock_mode = True

        if self.mock_mode:
            logging.info("DHT22 running in mock mode")

        self.start()

    def _read_sensor(self):
        """
        Read temperature and humidity from DHT22 sensor.
        """
        if self.mock_mode:
            import random

            base_temp = 22.0
            base_humidity = 55.0
            self.temperature_celsius = base_temp + random.uniform(-2.0, 2.0)
            self.humidity_percent = base_humidity + random.uniform(-5.0, 5.0)
        else:
            try:
                if self.sensor:
                    temp = self.sensor.temperature
                    hum = self.sensor.humidity

                    if temp is not None and hum is not None:
                        self.temperature_celsius = round(temp, 1)
                        self.humidity_percent = round(hum, 1)
                    else:
                        logging.debug("DHT22 sensor returned None values")
            except RuntimeError as e:
                # DHT sensors can occasionally fail to read, which is normal
                logging.debug(f"DHT22 read error (retrying): {e}")
            except Exception as e:
                logging.error(f"Unexpected error reading DHT22: {e}")

        self.last_read_time = time.time()
        self._update_data()

    def _update_data(self):
        """
        Update internal data structure with current readings.
        """
        self._data = {
            "temperature_celsius": self.temperature_celsius,
            "temperature_fahrenheit": self.temperature_celsius * 9 / 5 + 32,
            "humidity_percent": self.humidity_percent,
            "timestamp": self.last_read_time,
        }

    def start(self):
        """
        Start the DHT22 provider thread.
        """
        if self._thread and self._thread.is_alive():
            return

        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logging.info("DHT22 provider started")

    def _run(self):
        """
        Main loop for reading sensor data.
        DHT22 should not be read more frequently than once every 2 seconds.
        """
        while self.running:
            self._read_sensor()
            # DHT22 datasheet recommends 2 second intervals between reads
            time.sleep(2.0)

    def stop(self):
        """
        Stop the DHT22 provider.
        """
        self.running = False
        if self._thread:
            logging.info("Stopping DHT22 provider")
            self._thread.join(timeout=5)

        if self.sensor and not self.mock_mode:
            try:
                self.sensor.exit()
            except Exception as e:
                logging.debug(f"Error cleaning up DHT22 sensor: {e}")

    @property
    def data(self) -> Optional[dict]:
        """
        Get the current sensor readings.

        Returns
        -------
        Optional[dict]
            Dictionary containing temperature and humidity data,
            or None if no data is available yet
        """
        return self._data
