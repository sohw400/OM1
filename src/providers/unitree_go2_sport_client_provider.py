import logging
import multiprocessing as mp
import time
from dataclasses import dataclass, field
from queue import Full
from typing import Optional

from runtime.logging import LoggingConfig, get_logging_config, setup_logging

try:
    from unitree.unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from unitree.unitree_sdk2py.go2.sport.sport_client import SportClient
except ImportError:
    logging.error(
        "Unitree SDK or CycloneDDS not found. Please install the unitree_sdk2py package or CycloneDDS."
    )

from .singleton import singleton


@dataclass
class UnitreeGo2Action:
    """
    Unitree Go2 Action Data Class.

    This class holds the action data for the Unitree Go2 robot.
    """

    action: str
    args: dict = field(default_factory=dict)


def unitree_go2_action_processor(
    channel: str,
    action_queue: mp.Queue,
    logging_config: Optional[LoggingConfig] = None,
) -> None:
    """
    Process function for the Unitree Go2 Action Provider.

    This function runs in a separate process to periodically retrieve actions
    from the action queue and send them to the Unitree Go2 robot.

    Parameters
    ----------
    channel : str
        The channel to connect to the Unitree Go2 robot.
    action_queue : mp.Queue
        Queue for sending the actions to the Unitree Go2 robot.
    logging_config : LoggingConfig, optional
        Optional logging configuration. If provided, it will override the default logging settings.
    """

    setup_logging("unitree_go2_action_processor", logging_config=logging_config)

    try:
        ChannelFactoryInitialize(0, channel)
    except Exception as e:
        logging.error(f"Error initializing Unitree Go2 state channel: {e}")
        return

    try:
        sport_client = SportClient()
        sport_client.Init()
        sport_client.SetTimeout(10.0)
        logging.info("Unitree Go2 State Provider initialized successfully")
    except Exception as e:
        logging.error(f"Error initializing Unitree Go2 State Provider: {e}")
        return

    while True:
        try:
            action: UnitreeGo2Action = action_queue.get()
            if hasattr(sport_client, action.action):
                method = getattr(sport_client, action.action)
                if callable(method):
                    logging.info(
                        f"Executing unitree go2 action: {action.action} with args: {action.args}"
                    )
                    method(**action.args)
                else:
                    logging.error(
                        f"Unitree go2 action {action.action} is not callable."
                    )
        except Exception as e:
            logging.error(f"Error processing action: {e}")
            time.sleep(0.1)


@singleton
class UnitreeGo2SportClientProvider:
    """
    Unitree Go2 Sport Client Provider.
    This class provides a singleton instance of the Unitree Go2 Sport Client.
    """

    def __init__(self, channel: Optional[str] = None):
        """
        Initialize the Unitree Go2 Sport Client Provider.

        Parameters
        ----------
        channel : str, optional
            The channel to connect to the Unitree Go2 robot. Defaults to None.
        """
        logging.info("Booting Unitree Go2 Sport Client Provider")

        self.action_queue: mp.Queue[UnitreeGo2Action] = mp.Queue(maxsize=1)
        self._action_processor_thread: Optional[mp.Process] = None

        self.channel: Optional[str] = channel
        if channel:
            self.start(channel)

    def start(self, channel: str):
        """
        Start the Unitree Go2 Sport Client Provider.

        Parameters
        ----------
        channel : str
            The channel to connect to the Unitree Go2 robot.
        """
        if self._action_processor_thread and self._action_processor_thread.is_alive():
            logging.warning("Unitree Go2 action processor thread is already running.")
            return

        if not channel:
            logging.error(
                "Channel is not set. Cannot start Unitree Go2 Sport Client Provider."
            )
            return

        self.channel = channel

        self._action_processor_thread = mp.Process(
            target=unitree_go2_action_processor,
            args=(self.channel, self.action_queue, get_logging_config()),
            daemon=True,
        )
        self._action_processor_thread.start()
        logging.info(
            f"Unitree Go2 Sport Client Provider started on channel: {self.channel}"
        )

    def add_action(self, action: UnitreeGo2Action):
        """
        Add an action to the action queue.

        Parameters
        ----------
        action : UnitreeGo2Action
            The action to be added to the queue.
        """
        if (
            not self._action_processor_thread
            or not self._action_processor_thread.is_alive()
        ):
            logging.error("Action processor thread is not running. Cannot add action.")
            return

        try:
            self.action_queue.put(action, timeout=1.0)
            logging.info(f"Action {action.action} added to the queue.")
        except Full:
            logging.warning("Action queue is full. Action not added.")

    @property
    def is_running(self) -> bool:
        """
        Check if the Unitree Go2 Sport Client Provider is running.

        Returns
        -------
        bool
            True if the provider is running, False otherwise.
        """
        return (
            self._action_processor_thread and self._action_processor_thread.is_alive()
        )
