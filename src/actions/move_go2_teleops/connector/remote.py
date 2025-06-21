import json
import logging
import time
from enum import Enum

from om1_utils import ws

from actions.base import ActionConfig, ActionConnector
from actions.move_go2_teleops.interface import MoveInput
from providers import CommandStatus
from providers.unitree_go2_sport_client_provider import (
    UnitreeGo2Action,
    UnitreeGo2SportClientProvider,
)
from providers.unitree_go2_state_provider import UnitreeGo2StateProvider


class RobotState(Enum):
    STANDING = "standing"
    SITTING = "sitting"


class MoveGo2Remote(ActionConnector[MoveInput]):
    """
    MoveGo2Remote connector for the Move action.
    """

    def __init__(self, config: ActionConfig):
        """
        Initialize the MoveGo2Remote connector.

        Parameters
        ----------
        config : ActionConfig
            The configuration for the action connector.
        """
        super().__init__(config)

        api_key = getattr(config, "api_key", None)

        self.ws_client = ws.Client(
            url=f"wss://api.openmind.org/api/core/teleops/action?api_key={api_key}"
        )
        self.ws_client.start()
        self.ws_client.register_message_callback(self._on_message)

        self.unitree_state_provider = UnitreeGo2StateProvider()

        unitree_ethernet = getattr(config, "unitree_ethernet", None)
        self.unitree_go2_sport_client = UnitreeGo2SportClientProvider(
            channel=unitree_ethernet
        )

    def _on_message(self, message: str) -> None:
        """
        Callback function to handle incoming messages.

        Parameters
        ----------
        message : str
            The incoming message.
        """
        if not self.unitree_go2_sport_client.is_running:
            logging.error("Unitree Go2 Sport Client is not running.")
            return

        if self.unitree_state_provider.state == "jointLock":
            self.unitree_go2_sport_client.add_action(
                UnitreeGo2Action(action="BalanceStand")
            )

        try:
            command_status = CommandStatus.from_dict(json.loads(message))
            self.unitree_go2_sport_client.add_action(
                UnitreeGo2Action(
                    action="Move",
                    args={
                        "vx": command_status.vx,
                        "vy": command_status.vy,
                        "vyaw": command_status.vyaw,
                    },
                )
            )
            logging.info(
                f"Published command: {command_status.to_dict()} - latency: {(time.time() - float(command_status.timestamp)):.3f} seconds"
            )
        except Exception as e:
            logging.error(f"Error processing command status: {e}")

    async def connect(self, output_interface: MoveInput) -> None:
        """
        Connect to the output interface and publish the command.

        Parameters
        ----------
        output_interface : MoveInput
            The output interface for the action.
        """
        pass
