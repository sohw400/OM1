import logging
import subprocess
import time
import threading
from dataclasses import dataclass
from actions.base import ActionConfig, ActionConnector
from actions.move.interface import MoveInput
import time
import sys

try:
    from unitree.unitree_sdk2py.core.channel import ChannelSubscriber
    from unitree.unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient
    from unitree.unitree_sdk2py.g1.arm.g1_arm_action_client import action_map
except ImportError:
    logging.warning(
        "Unitree SDK not found. Please install the Unitree SDK to use this plugin."
    )

motions = [
    "shake hand",
    "high five", 
    "hug",
    "high wave",
    "clap",
    "face wave",
    "left kiss",
    "heart",
    "right heart",
    "hands up",
    "x-ray",
    "right hand up",
    "reject",
    "right kiss",
    "two-hand kiss"
]

class UnitreeG1SDKConnector(ActionConnector[MoveInput]):
    """
    A connector that publishes Move messages using Gazebo Topics.
    When a Move input is received, the connector publishes the message via the
    gz topic command
    """
    
    def __init__(self, config: ActionConfig):
        super().__init__(config)
        robot_name = getattr(self.config, "robot_name", None)
        unitree_ethernet = getattr(self.config, "unitree_ethernet", None)
        logging.info(f"UnitreeG1Basic using ethernet: {unitree_ethernet}")
        self.armAction_client = None
        
        # Joint angles e.g.
        if unitree_ethernet and unitree_ethernet != "":
            logging.info("Setting up the action client.")
            # only set up if we are connected to a robot
            self.armAction_client = G1ArmActionClient()
            self.armAction_client.SetTimeout(10.0)
            self.armAction_client.Init()

    def _execute_action_threaded(self, action, action_name):
        """Execute the action in a separate thread to prevent blocking"""
        try:
            logging.info(f"Executing action: {action_name}")
            self.armAction_client.ExecuteAction(action)
            logging.info(f"Action completed: {action_name}")
            # time.sleep(1.0)
            # self.armAction_client.ExecuteAction("release arm")
            # logging.info(f"Moved back arms")
        except Exception as e:
            logging.error(f"Error executing action: {e}")

    async def connect(self, output_interface: MoveInput) -> None:
        new_msg = {"move": ""}
        
        # Check if the output_interface.action matches any of our motions
        if output_interface.action in motions:
            new_msg["move"] = output_interface.action
            
            # Execute the action in a separate thread to prevent blocking
            if self.armAction_client:
                action_thread = threading.Thread(
                    target=self._execute_action_threaded,
                    args=(action_map.get(output_interface.action),output_interface.action),
                    daemon=True  # Dies when main thread dies
                )
                action_thread.start()
                logging.info(f"Action thread started for: {output_interface.action}")
        else:
            logging.warning(f"Unknown action: {output_interface.action}")

    def tick(self) -> None:
        time.sleep(0.1)