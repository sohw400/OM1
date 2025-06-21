import logging

from backgrounds.base import Background, BackgroundConfig
from providers.unitree_go2_sport_client_provider import UnitreeGo2SportClientProvider


class UnitreeGo2SportClient(Background):
    """
    Reads Unitree Go2 sport client from UnitreeGo2SportClientProvider.
    This background service initializes the Unitree Go2 Sport Client Provider
    and starts it with the specified Ethernet channel from the configuration.
    It is designed to run in the background, allowing for asynchronous communication
    with the Unitree Go2 robot's sport client.
    """

    def __init__(self, config: BackgroundConfig = BackgroundConfig()):
        super().__init__(config)

        unitree_ethernet = getattr(config, "unitree_ethernet", None)
        if not unitree_ethernet:
            logging.error(
                "Unitree Go2 Ethernet channel is not set in the configuration."
            )
            raise ValueError(
                "Unitree Go2 Ethernet channel must be specified in the configuration."
            )

        self.unitree_go_sport_client_provider = UnitreeGo2SportClientProvider()
        self.unitree_go_sport_client_provider.start(unitree_ethernet)
        logging.info("Unitree Go2 Sport Client Provider initialized in background")
