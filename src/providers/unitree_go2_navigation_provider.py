import logging
from typing import Optional
from uuid import uuid4

import zenoh
from zenoh import ZBytes

from zenoh_msgs import (
    geometry_msgs,
    nav_msgs,
    open_zenoh_session,
    AIStatusRequest,
    String,
    prepare_header,
)

from .singleton import singleton
from .io_provider import IOProvider

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
            The topic on which to subscribe for navigation messages (default is "navigate_to_pose/_action/status").
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
        # track whether a navigation goal is in progress
        self._nav_in_progress: bool = False
        # store the current goal ID for cancellation
        self._current_goal_id: Optional[str] = None
        
        # IO provider to communicate runtime variables (e.g., ai_enabled)
        try:
            self._io = IOProvider()
            # default to AI enabled unless explicitly disabled elsewhere
            self._io.add_dynamic_variable("ai_enabled", True)
        except Exception:
            self._io = None
        # declare ai status publisher topic
        self.ai_topic = "om/ai/request"
        self.ai_pub = None
        try:
            if self.session is not None:
                self.ai_pub = self.session.declare_publisher(self.ai_topic)
        except Exception:
            logging.exception("Failed to declare AI status publisher")

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
                
                # Manage AI enable/disable based on navigation state
                try:
                    if self._io is not None:
                        # If navigation is accepted or executing, ensure AI disabled
                        if latest_status.status in (1, 2):
                            self._io.add_dynamic_variable("ai_enabled", False)
                            self._nav_in_progress = True
                        # Terminal states -> re-enable AI
                        elif latest_status.status in (4, 5, 6):
                            self._io.add_dynamic_variable("ai_enabled", True)
                            self._nav_in_progress = False
                            
                            # Auto-cancel goal on success to prevent re-navigation
                            if latest_status.status == 4:  # SUCCEEDED
                                logging.info("Navigation succeeded, canceling goal to prevent re-navigation")
                                self._cancel_current_goal()
                    
                    # Also publish an AIStatusRequest to notify other processes
                    try:
                        if self.ai_pub is not None:
                            # for nav status messages we may not have a frame id; use 'map'
                            header = prepare_header("map")
                            code = 0 if latest_status.status in (1, 2) else 1 if latest_status.status in (4, 5, 6) else 1
                            status_msg = AIStatusRequest(
                                header=header,
                                request_id=String(str(uuid4())),
                                code=code,
                            )
                            self.ai_pub.put(status_msg.serialize())
                    except Exception:
                        logging.exception("Failed to publish AIStatusRequest from navigation status")
                except Exception:
                    logging.exception("Error updating AI enabled flag from navigation status")
        else:
            logging.warning("Received empty navigation status message")

    def _cancel_current_goal(self):
        """
        Internal method to cancel the current navigation goal.
        """
        if self.session is None:
            logging.error("Cannot cancel goal; Zenoh session is not available.")
            return
            
        try:
            # Create an empty cancel request or use the appropriate message type
            # For ROS2 actions, we typically send an empty goal ID to cancel the current goal
            # You may need to adjust this based on your zenoh_msgs implementation
            cancel_payload = ZBytes(b"")  # Empty payload to cancel current goal
            self.session.put(self.cancel_goal_topic, cancel_payload)
            logging.info("Sent cancellation request to topic: %s", self.cancel_goal_topic)
            self._current_goal_id = None
        except Exception:
            logging.exception("Failed to cancel navigation goal")

    def cancel_navigation(self):
        """
        Public method to manually cancel the current navigation goal.
        """
        logging.info("Manually canceling navigation goal")
        self._cancel_current_goal()
        
        # Re-enable AI immediately
        try:
            if self._io is not None:
                self._io.add_dynamic_variable("ai_enabled", True)
                self._nav_in_progress = False
        except Exception:
            logging.exception("Failed to re-enable AI after manual cancellation")

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
        
        # Generate a new goal ID
        self._current_goal_id = str(uuid4())
        
        # mark navigation in progress and disable AI while executing
        try:
            if self._io is not None:
                self._io.add_dynamic_variable("ai_enabled", False)
                self._nav_in_progress = True
        except Exception:
            logging.exception("Failed to set ai_enabled flag before publishing goal")
        
        # publish AIStatusRequest(code=0) so other processes know AI is disabled
        try:
            if self.ai_pub is not None:
                header = prepare_header("map")
                status_msg = AIStatusRequest(
                    header=header,
                    request_id=String(str(uuid4())),
                    code=0,
                )
                self.ai_pub.put(status_msg.serialize())
        except Exception:
            logging.exception("Failed to publish AIStatusRequest before publishing goal")

        payload = ZBytes(pose.serialize())
        self.session.put(self.goal_pose_topic, payload)
        logging.info("Published goal pose to topic: %s with goal_id: %s", 
                    self.goal_pose_topic, self._current_goal_id)

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