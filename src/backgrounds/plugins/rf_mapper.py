import asyncio
import logging
import threading
import time
from typing import Dict, List

from bleak import AdvertisementData, BleakScanner

from backgrounds.base import Background, BackgroundConfig
from providers.fabric_map_provider import (
    FabricData,
    FabricDataSubmitter,
    RFData,
    RFDataRaw,
)
from providers.gps_provider import GpsProvider
from providers.odom_provider import OdomProvider
from providers.rtk_provider import RtkProvider


class RFmapper(Background):
    """
    Assemble location and BLE data.
    """

    def __init__(self, config: BackgroundConfig = BackgroundConfig()):
        """
        Initialize the RFmapper with configuration.

        Parameters
        ----------
        config : BackgroundConfig
            Configuration object for the background.
        """
        super().__init__(config)

        logging.info(f"Mapper config: {config}")

        self.name = getattr(config, "name", "RFmapper")
        self.api_key = getattr(config, "api_key", None)
        self.URID = getattr(config, "URID", None)
        self.unitree_ethernet = getattr(config, "unitree_ethernet", None)

        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._scan_task)
        self.running = False
        self.scan_results: List[RFData] = []

        self.x = 0.0
        self.y = 0.0
        self.yaw_odom_0_360 = 0.0

        self.gps_time_utc = ""
        self.gps_lat = 0.0
        self.gps_lon = 0.0
        self.gps_alt = 0.0
        self.gps_qua = 0
        self.yaw_mag_0_360 = 0.0
        self.ble_scan: List[RFDataRaw] = []

        self.rtk_time_utc = ""
        self.rtk_lat = 0.0
        self.rtk_lon = 0.0
        self.rtk_alt = 0.0
        self.rtk_qua = 0

        self.gps = GpsProvider()
        self.gps_on = self.gps.running
        logging.info(f"Mapper Gps Provider: {self.gps}")

        self.rtk = RtkProvider()
        self.rtk_on = self.rtk.running
        logging.info(f"Mapper Rtk Provider: {self.rtk}")

        self.odom = OdomProvider()
        logging.info(f"Mapper Odom Provider: {self.odom}")

        self.fds = FabricDataSubmitter(api_key=self.api_key, write_to_local_file=True)

        self.seen_devices: Dict[str, RFData] = {}

        self.seen_names: List[str] = []

        self.start()

    async def scan(self):

        def detection_callback(device, advdata: AdvertisementData):

            addr = device.address

            local_name = None
            if device.name:
                local_name = device.name
            elif advdata.local_name:
                local_name = advdata.local_name

            # if local_name:
            #     logging.debug(f"Local name: {local_name}")
            #     self.seen_names.append(local_name)
            #     # keep the list unique
            #     self.seen_names = list(set(self.seen_names))
            # logging.info(f"{self.seen_names}")

            # AdvertisementData(
            # local_name: Optional[str],
            # manufacturer_data: Dict[int, bytes],
            # service_data: Dict[str, bytes],
            # service_uuids: List[str],
            # tx_power: Optional[int],
            # rssi: int, platform_data: Tuple)

            mfgkey = ""
            mfgval = ""
            service_uuid = ""

            if advdata.manufacturer_data:
                for key, value in advdata.manufacturer_data.items():
                    mfgkey = hex(key).upper()
                    mfgval = value.hex().upper()
                    break

            if advdata.service_uuids:
                service_uuid = advdata.service_uuids[0]

            # we want to update everything EXCEPT we do not want to overwrite a resolved name
            # and we do not want to replace a long mfgval with a short one
            # we also want to update the TX power if we receive those data
            rssi = advdata.rssi
            tx_power = advdata.tx_power

            if addr in self.seen_devices:
                self.seen_devices[addr].rssi = rssi
                self.seen_devices[addr].timestamp = time.time()
                if tx_power and self.seen_devices[addr].tx_power is None:
                    self.seen_devices[addr].tx_power = tx_power
                    logging.info(
                        f"Updated BLE tx_power: {self.seen_devices[addr].tx_power}"
                    )
                if local_name and self.seen_devices[addr].name is None:
                    self.seen_devices[addr].name = local_name
                    logging.info(f"Updated BLE name: {self.seen_devices[addr].name}")
                if len(mfgval) > len(self.seen_devices[addr].mfgval):
                    self.seen_devices[addr].mfgval = mfgval
                    logging.info(
                        f"Updated BLE mfgval: {self.seen_devices[addr].mfgval}"
                    )
            else:
                # this is a new device
                self.seen_devices[addr] = RFData(
                    timestamp=time.time(),
                    address=addr,
                    name=local_name if local_name else None,
                    rssi=rssi,
                    tx_power=tx_power if tx_power else None,
                    service_uuid=service_uuid,
                    mfgkey=mfgkey,
                    mfgval=mfgval,
                )

        scanner = BleakScanner(detection_callback)

        await scanner.start()
        await asyncio.sleep(10.0)
        await scanner.stop()

        logging.debug(f"ready to sort: {self.seen_devices.values()}")

        # Get the top 20 devices with the strongest RSSI
        sorted_devices = sorted(
            self.seen_devices.values(), key=lambda d: d.rssi, reverse=True
        )

        final_list: List[RFData] = []
        for i, device in enumerate(sorted_devices):
            # return all the strong ones, or, the ones with a local name
            # some will be both, but that's good
            if i < 20 or device.name:
                final_list.append(device)
        logging.debug(f"Scan...{final_list}")
        return final_list

    def _scan_task(self):
        asyncio.set_event_loop(self.loop)
        logging.info("Starting RF scan thread...")
        self.running = True
        while self.running:
            self.scan_results = self.loop.run_until_complete(self.scan())
            time.sleep(1)

    def start(self):
        self.thread.start()

    def stop(self):
        self.running = False
        time.sleep(1)
        self.thread.join()

    def run(self) -> None:
        """
        Run the background process.
        This method will run indefinitely, simulating a long-running task.
        """
        try:
            while self.running:
                if self.scan_results:
                    logging.debug(
                        f"RF scan results available, processing... {self.scan_results}"
                    )
                    try:
                        g = self.gps.data
                        logging.debug(f"GPS data: {g}")
                        if g:

                            if g["gps_time_utc"] != "":
                                self.gps_time_utc = g["gps_time_utc"]
                                self.gps_lat = g["gps_lat"]
                                self.gps_lon = g["gps_lon"]
                                self.gps_alt = g["gps_alt"]
                                self.yaw_mag_0_360 = g["yaw_mag_0_360"]
                                self.gps_qua = g["gps_qua"]

                            if g["ble_scan"] is not None:
                                self.ble_scan = g["ble_scan"]
                                logging.debug(f"RF scan results {self.ble_scan}")
                            else:
                                logging.warn("No nRF52 scan results")

                    except Exception as e:
                        logging.error(f"Error parsing GPS: {e}")

                    try:
                        o = self.odom.position
                        logging.debug(f"Odom data: {o}")
                        if o:
                            self.x = o["x"]
                            self.y = o["y"]
                            self.yaw_odom_0_360 = o["yaw_odom_0_360"]
                    except Exception as e:
                        logging.error(f"Error parsing Odom: {e}")

                    if hasattr(self.rtk, "running"):
                        try:
                            r = self.rtk.data
                            logging.debug(f"RTK data: {r}")
                            if r:
                                self.rtk_time_utc = r["rtk_time_utc"]
                                self.rtk_lat = r["rtk_lat"]
                                self.rtk_lon = r["rtk_lon"]
                                self.rtk_alt = r["rtk_alt"]
                                self.rtk_qua = r["rtk_qua"]
                        except Exception as e:
                            logging.error(f"Error parsing RTK: {e}")

                    try:
                        self.fds.share_data(
                            FabricData(
                                machine_id=self.URID,
                                gps_time_utc=self.gps_time_utc,
                                gps_lat=self.gps_lat,
                                gps_lon=self.gps_lon,
                                gps_alt=self.gps_alt,
                                gps_qua=self.gps_qua,
                                rtk_time_utc=self.rtk_time_utc,
                                rtk_lat=self.rtk_lat,
                                rtk_lon=self.rtk_lon,
                                rtk_alt=self.rtk_alt,
                                rtk_qua=self.rtk_qua,
                                mag=self.yaw_mag_0_360,
                                update_time_local=time.time(),
                                odom_x=self.x,
                                odom_y=self.y,
                                yaw_odom_0_360=self.yaw_odom_0_360,
                                yaw_odom_m180_p180=self.yaw_odom_0_360 - 180.0,
                                rf_data=self.scan_results,
                                rf_data_raw=self.ble_scan,
                            )
                        )
                    except Exception as e:
                        logging.error(f"Error sharing to Fabric: {e}")

                    self.scan_results = []

                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Stopping RF scanner...")
            self.stop()
