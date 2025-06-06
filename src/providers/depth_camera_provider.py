import logging
import threading
import time
from typing import Dict, Optional

import numpy as np
import pyrealsense2 as rs

from providers.singleton import singleton

logger = logging.getLogger(__name__)


@singleton
class DepthCameraProvider:
    """Provider for depth camera collision avoidance using Intel RealSense.

    This provider reads depth data from a downward-facing camera and detects
    obstacles beneath the robot for collision avoidance.
    """

    def __init__(
        self,
        depth_threshold: float = 0.3,  # Minimum safe distance in meters
        detection_width: float = 0.5,  # Width of detection area in meters
        detection_length: float = 0.6,  # Length of detection area in meters
        fps: int = 15,
        width: int = 640,
        height: int = 480,
    ):
        """Initialize the depth camera provider.

        Args:
            depth_threshold: Minimum safe distance to ground/obstacles in meters
            detection_width: Width of the detection area in meters
            detection_length: Length of the detection area in meters
            fps: Frames per second for the depth camera
            width: Width of the depth image
            height: Height of the depth image
        """
        self.depth_threshold = depth_threshold
        self.detection_width = detection_width
        self.detection_length = detection_length
        self.fps = fps
        self.width = width
        self.height = height

        # RealSense pipeline
        self.pipeline = None
        self.config = None
        self.depth_scale = 0.001  # Default value, will be updated from sensor

        # Thread management
        self._thread = None
        self._running = False
        self._lock = threading.Lock()  # Thread safety for shared state

        # Obstacle detection results
        self._obstacle_detected = False
        self._safe_direction = "forward"
        self._obstacle_info = ""
        self._depth_frame = None

        # Detection zones (relative to image center)
        self._zones = {
            "center": {"detected": False, "distance": None},
            "left": {"detected": False, "distance": None},
            "right": {"detected": False, "distance": None},
            "front": {"detected": False, "distance": None},
            "back": {"detected": False, "distance": None},
        }

    def start(self):
        """Start the depth camera provider."""
        if self._running:
            logger.warning("Depth camera provider already running")
            return

        try:
            # Check if any RealSense device is connected
            ctx = rs.context()
            devices = ctx.query_devices()
            if len(devices) == 0:
                raise RuntimeError("No RealSense device connected")

            # Configure RealSense pipeline
            self.pipeline = rs.pipeline()
            self.config = rs.config()

            # Enable depth stream
            self.config.enable_stream(
                rs.stream.depth, self.width, self.height, rs.format.z16, self.fps
            )

            # Start pipeline
            profile = self.pipeline.start(self.config)

            # Get depth sensor
            depth_sensor = profile.get_device().first_depth_sensor()

            # Set depth units (usually 0.001 for mm to m conversion)
            self.depth_scale = depth_sensor.get_depth_scale()
            logger.info(f"Depth scale: {self.depth_scale}")

            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

            logger.info("Depth camera provider started successfully")

        except Exception as e:
            logger.error(f"Failed to start depth camera: {e}")
            self._running = False
            if self.pipeline:
                self.pipeline.stop()

    def stop(self):
        """Stop the depth camera provider."""
        logger.info("Stopping depth camera provider")
        self._running = False

        if self._thread:
            self._thread.join(timeout=5.0)

        if self.pipeline:
            try:
                self.pipeline.stop()
            except Exception as e:
                logger.debug(f"Error stopping pipeline: {e}")

        logger.info("Depth camera provider stopped")

    def _run(self):
        """Main processing loop running in separate thread."""
        while self._running:
            try:
                # Wait for frames
                frames = self.pipeline.wait_for_frames(timeout_ms=1000)

                # Get depth frame
                depth_frame = frames.get_depth_frame()
                if not depth_frame:
                    continue

                # Convert to numpy array
                depth_image = np.asanyarray(depth_frame.get_data())

                # Process depth data
                self._process_depth_frame(depth_image)

                # Store frame for external access (thread-safe)
                with self._lock:
                    self._depth_frame = depth_image.copy()

            except Exception as e:
                if self._running:  # Only log if we're supposed to be running
                    logger.error(f"Error in depth processing loop: {e}")
                time.sleep(0.1)

    def _process_depth_frame(self, depth_image: np.ndarray):
        """Process depth frame to detect obstacles.

        Args:
            depth_image: Depth image as numpy array (values in mm)
        """
        # Convert depth values from mm to meters using sensor's depth scale
        depth_m = depth_image * self.depth_scale

        # Get image dimensions
        h, w = depth_image.shape

        # Define detection zones (5 zones: center, left, right, front, back)
        zone_width = w // 3
        zone_height = h // 3

        zones_config = {
            "center": (zone_width, zone_width * 2, zone_height, zone_height * 2),
            "left": (0, zone_width, zone_height, zone_height * 2),
            "right": (zone_width * 2, w, zone_height, zone_height * 2),
            "front": (zone_width, zone_width * 2, 0, zone_height),
            "back": (zone_width, zone_width * 2, zone_height * 2, h),
        }

        # Analyze each zone
        obstacle_in_any_zone = False
        obstacles = []

        for zone_name, (x1, x2, y1, y2) in zones_config.items():
            # Extract zone
            zone = depth_m[y1:y2, x1:x2]

            # Filter valid depth values (ignore 0 values which mean no reading)
            valid_depths = zone[zone > 0]

            if len(valid_depths) > 0:
                # Get minimum distance in zone
                min_distance = np.min(valid_depths)

                # Check if obstacle detected
                if min_distance < self.depth_threshold:
                    zone_update = {"detected": True, "distance": min_distance}
                    obstacle_in_any_zone = True
                    obstacles.append(f"{zone_name}: {min_distance:.2f}m")
                else:
                    zone_update = {"detected": False, "distance": min_distance}
            else:
                zone_update = {"detected": False, "distance": None}

            # Thread-safe update
            with self._lock:
                self._zones[zone_name].update(zone_update)

        # Update obstacle detection status and other shared state
        with self._lock:
            self._obstacle_detected = obstacle_in_any_zone

            # Determine safe direction based on obstacles
            self._determine_safe_direction()

            # Update obstacle info string
            if obstacles:
                self._obstacle_info = f"Obstacles detected at: {', '.join(obstacles)}"
            else:
                self._obstacle_info = "Path clear"

    def _determine_safe_direction(self):
        """Determine the safest direction to move based on obstacle zones."""
        center = self._zones["center"]["detected"]
        left = self._zones["left"]["detected"]
        right = self._zones["right"]["detected"]
        front = self._zones["front"]["detected"]
        back = self._zones["back"]["detected"]

        # Decision logic for safe direction
        if not center and not front:
            # Clear ahead
            self._safe_direction = "forward"
        elif center or front:
            # Obstacle ahead, check sides
            if not left and not right:
                # Both sides clear, prefer slight turn
                self._safe_direction = "turn_left"
            elif not left:
                self._safe_direction = "turn_left"
            elif not right:
                self._safe_direction = "turn_right"
            elif back:
                # Front and sides blocked, but back has obstacle too
                self._safe_direction = "retreat"  # Still retreat but carefully
            else:
                # All directions blocked, retreat
                self._safe_direction = "retreat"
        elif left and not right:
            self._safe_direction = "turn_right"
        elif right and not left:
            self._safe_direction = "turn_left"
        elif back and not center and not front:
            # Only back has obstacle, safe to go forward
            self._safe_direction = "forward"
        else:
            # Default to retreat if confused
            self._safe_direction = "retreat"

    @property
    def obstacle_detected(self) -> bool:
        """Check if any obstacle is detected."""
        with self._lock:
            return self._obstacle_detected

    @property
    def safe_direction(self) -> str:
        """Get the recommended safe direction to move."""
        with self._lock:
            return self._safe_direction

    @property
    def obstacle_info(self) -> str:
        """Get human-readable obstacle information."""
        with self._lock:
            return self._obstacle_info

    @property
    def movement_options(self) -> Dict[str, bool]:
        """Get movement options similar to lidar provider format."""
        with self._lock:
            return {
                "turn_left": self._safe_direction == "turn_left"
                or not self._zones["left"]["detected"],
                "advance": self._safe_direction == "forward",
                "turn_right": self._safe_direction == "turn_right"
                or not self._zones["right"]["detected"],
                "retreat": self._safe_direction == "retreat",
            }

    @property
    def obstacle_string(self) -> str:
        """Get obstacle description for LLM consumption."""
        with self._lock:
            if not self._obstacle_detected:
                return "Ground surface clear, safe to proceed forward"

            # Build detailed description
            parts = []
            for zone, data in self._zones.items():
                if data["detected"]:
                    parts.append(f"{zone} ({data['distance']:.2f}m)")

            obstacle_desc = f"Obstacles detected below: {', '.join(parts)}. "

            # Add movement recommendation
            if self._safe_direction == "forward":
                obstacle_desc += "Safe to move forward."
            elif self._safe_direction == "turn_left":
                obstacle_desc += "Recommend turning left."
            elif self._safe_direction == "turn_right":
                obstacle_desc += "Recommend turning right."
            elif self._safe_direction == "retreat":
                obstacle_desc += "Recommend moving backward."

            return obstacle_desc

    @property
    def zones(self) -> Dict:
        """Get detailed zone information."""
        with self._lock:
            return self._zones.copy()

    @property
    def is_running(self) -> bool:
        """Check if the provider is running."""
        return self._running

    @property
    def depth_frame(self) -> Optional[np.ndarray]:
        """Get the latest depth frame (thread-safe copy)."""
        with self._lock:
            return self._depth_frame.copy() if self._depth_frame is not None else None
