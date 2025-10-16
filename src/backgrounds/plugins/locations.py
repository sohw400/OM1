import logging

from backgrounds.base import Background, BackgroundConfig
from providers.locations_provider import LocationsProvider


class Locations(Background):
    """
    Reads locations from LocationsProvider.
    """

    def __init__(self, config: BackgroundConfig = BackgroundConfig()):
        """
        Initialize the Locations background task.

        Parameters
        ----------
        config : BackgroundConfig
            Configuration for the background task.
        """
        super().__init__(config)

        location_endpoint = getattr(
            self.config,
            "location_endpoint",
            "http://localhost:5000/maps/locations/list",
        )
        timeout = getattr(self.config, "timeout", 5)
        refresh_interval = getattr(self.config, "refresh_interval", 30)

        if not location_endpoint:
            logging.warning("Locations background: list_endpoint not configured")

        self.locations_provider = LocationsProvider(
            location_endpoint=location_endpoint,
            timeout=timeout,
            refresh_interval=refresh_interval,
        )
        self.locations_provider.start()

        logging.info(
            f"Locations Provider initialized in background (endpoint: {location_endpoint}, refresh: {refresh_interval}s)"
        )
