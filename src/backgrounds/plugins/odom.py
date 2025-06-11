import logging

from backgrounds.base import Background, BackgroundConfig
from providers.odom_provider import OdomProvider


class Odom(Background):
    """
    Reads odometry data from Odom provider.
    """

    def __init__(self, config: BackgroundConfig = BackgroundConfig()):
        super().__init__(config)

        use_zenoh = getattr(config, "use_zenoh", False)
        self.URID = getattr(config, "URID", "")
        if use_zenoh:
            logging.info(
                f"RPLidar using Zenoh and URID: {self.URID} in Odom background"
            )

        self.odom_provider = OdomProvider(self.URID, use_zenoh)
        if use_zenoh:
            logging.info(f"Odom using Zenoh with URID: {self.URID} in Odom background")
        else:
            logging.info("Odom provider initialized without Zenoh in Odom background")
