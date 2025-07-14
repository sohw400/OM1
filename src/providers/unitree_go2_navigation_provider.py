import logging

import zenoh

from zenoh_idl import nav_msgs

from .singleton import singleton
from .zenoh_listener_provider import ZenohListenerProvider

status_map = {
    0: "UNKNOWN",
    1: "ACCEPTED",
    2: "EXECUTING",
    3: "CANCELING",
    4: "SUCCEEDED",
    5: "CANCELED",
    6: "ABORTED",
}


@singleton
class UnitreeGo2NavigationProvider(ZenohListenerProvider):
    """
    AMCL Provider for Unitree Go2 robot.
    """

    def __init__(self, topic: str = "navigate_to_pose/_action/status"):
        """
        Initialize the Unitree Go2 Navigation Provider with a specific topic.

        Parameters
        ----------
        topic : str, optional
            The topic on which to subscribe for navigation messages (default is "navigate_to_pose/_action/status").
        """
        super().__init__(topic)
        logging.info(
            "Unitree Go2 Navigation Provider initialized with topic: %s", topic
        )

        self.navigation_status = "UNKNOWN"

    def navigation_status_message_callback(self, data: zenoh.Sample):
        """
        Process an incoming navigation status message.

        Parameters
        ----------
        data : zenoh.Sample
            The Zenoh sample received, which should have a 'payload' attribute.
        """
        if data.payload:
            message: nav_msgs.Nav2Status = nav_msgs.Nav2Status.deserialize(
                data.payload.to_bytes()
            )
            logging.debug("Received Navigation Status message: %s", message)
            status_list = message.status_list
            if status_list:
                latest_status = status_list[-1]
                logging.info("Latest Navigation Status: %s", latest_status)
                self.navigation_status = status_map.get(latest_status.status, "UNKNOWN")
                logging.info("Navigation Status: %s", self.navigation_status)
        else:
            logging.warning("Received empty navigation status message")

    def start(self):
        """
        Start the navigation provider by registering the message callback and starting the listener.
        """
        if not self.running:
            self.register_message_callback(self.navigation_status_message_callback)
            self.running = True
            logging.info("Navigation Provider started and listening for messages")
        else:
            logging.warning("Navigation Provider is already running")

    @property
    def navigation_state(self) -> str:
        """
        Get the current navigation state.

        Returns
        -------
        str
            The current navigation state as a string.
        """
        return self.navigation_status
