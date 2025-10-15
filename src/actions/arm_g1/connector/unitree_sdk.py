import logging

from actions.arm_g1.interface import ArmInput
from actions.base import ActionConfig, ActionConnector
from unitree.unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient


class ARMUnitreeSDKConnector(ActionConnector[ArmInput]):

    def __init__(self, config: ActionConfig):
        super().__init__(config)

        try:
            self.client = G1ArmActionClient()
            self.client.SetTimeout(10.0)
            self.client.Init()
            logging.info("G1 Arm Action Client initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize G1 Arm Action Client: {e}")

    async def connect(self, output_interface: ArmInput) -> None:
        """
        Connects to the G1 Arm Action Client and executes the specified action.
        """
        logging.info(f"AI command.action: {output_interface.action}")

        if output_interface.action == "idle":
            logging.info("No action to perform, returning.")
            return

        if output_interface.action == "left kiss":
            action_id = 12

        if output_interface.action == "right kiss":
            action_id = 13

        if output_interface.action == "clap":
            action_id = 17

        if output_interface.action == "high five":
            action_id = 18

        if output_interface.action == "shake hand":
            action_id = 27

        if output_interface.action == "heart":
            action_id = 20

        if output_interface.action == "high wave":
            action_id = 26

        logging.info(f"Executing action with ID: {action_id}")

        self.client.ExecuteAction(action_id)
