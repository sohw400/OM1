import asyncio
import json
import logging
from typing import Any, Optional

import aiohttp

from actions.base import ActionConfig, ActionConnector
from actions.navigate_location.interface import NavigateLocationInput
from providers.unitree_go2_navigation_provider import UnitreeGo2NavigationProvider
from providers.http_locations_provider import HTTPLocationsProvider
from providers.io_provider import IOProvider
from zenoh_msgs import geometry_msgs
from zenoh_msgs import Header, Point, Pose, PoseStamped, Quaternion, Time


class HTTPNavConnector(ActionConnector[NavigateLocationInput]):
    """
    Connector that queries a locations API and publishes a navigation goal.

    Config options:
      - list_endpoint: URL to GET available locations (required)
      - timeout: request timeout seconds (default 5)
    """

    def __init__(self, config: ActionConfig):
        super().__init__(config)
        self.list_endpoint: Optional[str] = getattr(config, "list_endpoint", None)
        self.timeout: int = getattr(config, "timeout", 5)
        self.provider = UnitreeGo2NavigationProvider()
        # provider that manages remote location lists
        self.loc_provider = HTTPLocationsProvider(self.list_endpoint or "", self.timeout, getattr(config, "refresh_interval", 0))
        self.io = IOProvider()

    async def connect(self, input_protocol: NavigateLocationInput) -> None:
        label = input_protocol.label

        # Use provider to lookup
        loc = self.loc_provider.get_location(label)
        if loc is None:
            # provide human-friendly feedback via IOProvider
            avail = self.loc_provider.get_all_locations()
            avail_list = ", ".join([str(v.get("name") if isinstance(v, dict) else k) for k, v in avail.items()])
            msg = f"Location '{label}' not found. Available: {avail_list}" if avail_list else f"Location '{label}' not found. No locations available."
            logging.warning(msg)
            self.io.add_input("NavigationResult", msg, None)
            return

        pose = loc.get("pose") or {}
        position = pose.get("position", {})
        orientation = pose.get("orientation", {})

        # Build PoseStamped using explicit sub-objects (same pattern as UnitreeGo2LocationProvider)
        # fill timestamp using real unix ts
        now = Time(sec=int(asyncio.get_event_loop().time()), nanosec=0)
        header = Header(stamp=now, frame_id="map")

        position_msg = Point(
            x=float(position.get("x", 0.0)),
            y=float(position.get("y", 0.0)),
            z=float(position.get("z", 0.0)),
        )
        orientation_msg = Quaternion(
            x=float(orientation.get("x", 0.0)),
            y=float(orientation.get("y", 0.0)),
            z=float(orientation.get("z", 0.0)),
            w=float(orientation.get("w", 1.0)),
        )
        pose_msg = Pose(position=position_msg, orientation=orientation_msg)

        goal_pose = PoseStamped(header=header, pose=pose_msg)

        try:
            self.provider.publish_goal_pose(goal_pose)
            msg = f"Navigation to '{label}' initiated"
            logging.info(msg)
            self.io.add_input("NavigationResult", msg, None)
        except Exception as e:
            logging.error(f"Error querying location list or publishing goal: {e}")
            self.io.add_input("NavigationResult", f"Error initiating navigation: {e}", None)

    def tick(self) -> None:
        # no periodic work
        return
