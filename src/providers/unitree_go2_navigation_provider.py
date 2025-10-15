"""
Navigation Provider for Unitree Go2 robot with AI mode control.

This provider listens to ROS2 navigation action status topic and manages:
1. Navigation goal publishing
2. Navigation status tracking
3. Automatic AI mode control based on navigation state

AI Mode Control Logic:
- When navigation starts (ACCEPTED/EXECUTING): AI mode is DISABLED
- When navigation succeeds (STATUS_SUCCEEDED=4): AI mode is RE-ENABLED
- When navigation fails/canceled (CANCELED/ABORTED): AI mode REMAINS DISABLED

This ensures the robot's autonomous behaviors don't interfere during navigation,
and AI is only restored after successful navigation completion.

ROS2 Topics:
- Subscribes: /navigate_to_pose/_action/status (or _action/feedback)
- Publishes: /goal_pose (navigation goals)
- Publishes: /navigate_to_pose/_action/cancel_goal (goal cancellation)
- Publishes: om/ai/request (AI enable/disable control)
"""

import logging
from typing import Optional
from uuid import uuid4

import zenoh
from zenoh import ZBytes

from zenoh_msgs import geometry_msgs, nav_msgs, open_zenoh_session

from .singleton import singleton
from .io_provider import IOProvider

# Nav2 Action Status Codes
status_map = {
    0: "UNKNOWN",
    1: "ACCEPTED",
    2: "EXECUTING",
    3: "CANCELING",
    4: "SUCCEEDED",  # Only this status re-enables AI mode
    5: "CANCELED",
    6: "ABORTED",
}


@singleton
class UnitreeGo2NavigationProvider:
    """
    Navigation Provider for Unitree Go2 robot.
    """

    def __init__(
        self,
        navigation_status_topic: str = "navigate_to_pose/_action/status",
        goal_pose_topic: str = "goal_pose",
        cancel_goal_topic: str = "navigate_to_pose/_action/cancel_goal",
    ):
        """
        Initialize the Unitree Go2 Navigation Provider with a specific topic.
        Parameters
        ----------
        navigation_status_topic : str, optional
            The ROS2 topic to subscribe for navigation status messages.
            Default: "navigate_to_pose/_action/status"
            Alternative: "navigate_to_pose/_action/feedback" for more detailed updates
        goal_pose_topic : str, optional
            The topic on which to publish goal poses (default is "goal_pose").
        cancel_goal_topic : str, optional
            The topic on which to publish goal cancellations (default is "navigate_to_pose/_action/cancel_goal").
        """
        self.session: Optional[zenoh.Session] = None

        try:
            self.session = open_zenoh_session()
            logging.info("Zenoh client opened")
        except Exception as e:
            logging.error(f"Error opening Zenoh client: {e}")

        self.navigation_status_topic = navigation_status_topic
        self.navigation_status = "UNKNOWN"

        self.goal_pose_topic = goal_pose_topic
        self.cancel_goal_topic = cancel_goal_topic

        self.running: bool = False

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
                latest_status = status_list[-1]  # type: ignore
                logging.info("Latest Navigation Status: %s", latest_status)
                self.navigation_status = status_map.get(latest_status.status, "UNKNOWN")
                logging.info("Navigation Status: %s", self.navigation_status)
        else:
            logging.warning("Received empty navigation status message")

    def start(self):
        """
        Start the navigation provider by registering the message callback and starting the listener.
        """
        if self.session is None:
            logging.error(
                "Cannot start navigation provider; Zenoh session is not available."
            )
            return

        if not self.running:
            self.session.declare_subscriber(
                self.navigation_status_topic, self.navigation_status_message_callback
            )
            logging.info(
                "Subscribed to navigation status topic: %s",
                self.navigation_status_topic,
            )

            self.running = True
            logging.info("Navigation Provider started and listening for messages")
            return

        logging.warning("Navigation Provider is already running")

    def publish_goal_pose(self, pose: geometry_msgs.PoseStamped):
        """
        Publish a goal pose to the navigation topic.
        Parameters
        ----------
        pose : geometry_msgs.PoseStamped
            The goal pose to be published.
        """
        if self.session is None:
            logging.error("Cannot publish goal pose; Zenoh session is not available.")
            return

        payload = ZBytes(pose.serialize())
        self.session.put(self.goal_pose_topic, payload)
        logging.info("Published goal pose to topic: %s with goal_id: %s", 
                    self.goal_pose_topic, self._current_goal_id)

    def clear_goal_pose(self):
        """
        Clear/cancel all active navigation goals.
        Publishes to the cancel_goal topic to stop navigation.
        """
        if self.session is None:
            logging.error("Cannot cancel goal; Zenoh session is not available.")
            return
            
        try:
            # Send cancel request to Nav2
            # Empty payload should cancel all active goals
            cancel_payload = ZBytes(b"")
            self.session.put(self.cancel_goal_topic, cancel_payload)
            logging.info("📍 Sent cancel all goals request to: %s", self.cancel_goal_topic)
            self._nav_in_progress = False
        except Exception:
            logging.exception("Failed to cancel navigation goals")

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

    @property
    def is_navigating(self) -> bool:
        """
        Check if navigation is currently in progress.
        Returns
        -------
        bool
            True if navigation is in progress, False otherwise.
        """
        return self._nav_in_progress

    @property
    def is_navigating(self) -> bool:
        """
        Check if navigation is currently in progress.
        Returns
        -------
        bool
            True if navigation is in progress, False otherwise.
        """
        return self._nav_in_progress