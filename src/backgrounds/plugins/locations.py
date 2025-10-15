import logging

from backgrounds.base import Background, BackgroundConfig
from providers.locations_provider import LocationsProvider


class Locations(Background):
    """
    Reads locations from LocationsProvider.
    """

    def __init__(self, config: BackgroundConfig = BackgroundConfig()):
        super().__init__(config)
        
        endpoint = getattr(config, "list_endpoint", "")
        timeout = getattr(config, "timeout", 5)
        refresh_interval = getattr(config, "refresh_interval", 30)  # Default 30 seconds
        
        if not endpoint:
            logging.warning("Locations background: list_endpoint not configured")
        
        self.locations_provider = LocationsProvider(
            list_endpoint=endpoint,
            timeout=timeout,
            refresh_interval=refresh_interval
        )
        self.locations_provider.start()
        
        logging.info(f"Locations Provider initialized in background (endpoint: {endpoint}, refresh: {refresh_interval}s)")
