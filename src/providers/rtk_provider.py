import logging
import threading
import time
from typing import Optional

import serial
from pynmeagps import NMEAReader

from .singleton import singleton


@singleton
class RtkProvider:
    """
    RTK Provider.

    This class implements a singleton pattern to manage:
        * RTK data from serial

    Parameters
    ----------
    serial_port: str = ""
    """

    def __init__(self, serial_port: str = ""):
        """
        Robot and sensor configuration
        """

        logging.info("Booting RTK Provider")

        baudrate = 115200
        timeout = 1

        self.serial_connection = None
        try:
            self.serial_connection = serial.Serial(
                serial_port, baudrate, timeout=timeout
            )
            logging.info(f"Connected to {serial_port} at {baudrate} baud")
        except serial.SerialException as e:
            logging.error(f"Error: {e}")

        if self.serial_connection:
            self.nmr = NMEAReader(self.serial_connection)
        else:
            self.nmr = None

        self._rtk: Optional[dict] = None

        self.lat = 0.0
        self.lon = 0.0
        self.alt = 0.0
        self.sat = 0
        self.qua = 0
        self.date_utc = ""
        self.time_utc = ""

        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.start()

    def magRTKProcessor(self, msg):
        # Used whenever there is a connected
        # nav Arduino on serial
        try:
            logging.debug(f"RTK:{msg}")

            if msg.msgID == "GGA":
                try:
                    # round to 10 cm localisation in x,y, and 1 cm in z
                    logging.debug(f"RTK GGA:{msg}")

                    self.lat = round(float(msg.lat), 6)
                    self.lon = round(float(msg.lon), 6)
                    self.alt = round(float(msg.alt), 2)

                    self.sat = int(msg.numSV)
                    self.qua = int(msg.quality)
                    ms = msg.time.strftime("%f")[:3]
                    # rtk_time_utc='15:51:23:800', rtk_date_utc='2025-06-17
                    # let's combine them for consitency
                    self.time_utc = (
                        self.date_utc + ":" + msg.time.strftime("%H:%M:%S") + ":" + ms
                    )
                    logging.debug(
                        (
                            f"Current precision location is {self.lat}, {self.lon} at {self.alt}m altitude. "
                            f"Quality {self.qua} with {self.sat} satellites locked. "
                            f"The date and time is {self.time_utc}."
                        )
                    )
                except Exception as e:
                    logging.warning(f"Failed to parse GGA message: {msg} ({e})")
            elif msg.msgID == "RMC":
                try:
                    self.date_utc = msg.date.strftime("%Y-%m-%d")
                    self.date_utc = self.date_utc.replace("-", ":")
                    logging.debug((f"The UTC date is {self.date_utc}."))
                except Exception as e:
                    logging.warning(f"Failed to parse RMC message: {msg} ({e})")
        except Exception as e:
            logging.warning(f"Error processing serial RTK input: {msg} ({e})")

        self._rtk = {
            "rtk_lat": self.lat,
            "rtk_lon": self.lon,
            "rtk_alt": self.alt,
            "rtk_sat": self.sat,
            "rtk_qua": self.qua,
            "rtk_time_utc": self.time_utc,
        }

    def start(self):
        """
        Starts the RTK Provider and processing thread
        if not already running.
        """
        if self._thread and self._thread.is_alive():
            return

        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        """
        Main loop for the RTK provider.
        """
        while self.running:

            if self.serial_connection and self.nmr:
                try:
                    (raw_data, parsed_data) = self.nmr.read()
                    if parsed_data:
                        self.magRTKProcessor(parsed_data)
                except Exception:
                    pass

                # # Read a line, decode, and remove whitespace
                # data = self.serial_connection.readline().decode("utf-8").strip()
                # logging.debug(f"Serial RTK: {data}")
                # self.magRTKProcessor(data)

            time.sleep(0.05)

    def stop(self):
        """
        Stop the RTK provider.
        """
        self.running = False
        if self._thread:
            logging.info("Stopping RTK provider")
            self._thread.join(timeout=5)

    @property
    def data(self) -> Optional[dict]:
        """
        Get the current robot RTK data.

        Returns
        -------
        Optional[dict]
            Dictionary containing RTK position data or None if not available
        """
        return self._rtk
