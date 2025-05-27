import logging
import math
import threading
import time
from typing import Optional

import zenoh

try:
    # Needed for Unitree but not TurtleBot4
    from unitree.unitree_sdk2py.core.channel import ChannelSubscriber
    from unitree.unitree_sdk2py.idl.geometry_msgs.msg.dds_ import PoseStamped_
except ImportError:
    logging.warning(
        "Unitree SDK or CycloneDDS not found. You do not need this unless you are connecting to a Unitree robot."
    )

from zenoh_idl import nav_msgs

from .singleton import singleton

rad_to_deg = 57.2958

gOdom = None


# Needed for Zenoh / TurtleBot4
def listenerOdom(data):
    global gOdom
    gOdom = nav_msgs.Odometry.deserialize(data.payload.to_bytes())
    logging.debug(f"Odom listener: {gOdom}")


@singleton
class OdomProvider:
    """
    Odom Provider.

    This class implements a singleton pattern to manage:
        * Odom and pose data using either Zenoh or CycloneDDS

    Parameters
    ----------
    URID: str = ""
        The URID needed to connect to the right Zenoh publisher in the local network
    use_zenoh: bool = False
        If true, get odom/pose data from Zenoh - typically used by TurtleBot4
        Otherwise, use CycloneDDS
    """

    def __init__(self, URID: str = "", use_zenoh: bool = False):
        """
        Robot and sensor configuration
        """

        logging.info("Booting Odom Provider")

        self.use_zenoh = use_zenoh
        self.URID = URID

        if self.use_zenoh:
            # typically, TurtleBot4
            if URID is None:
                logging.warning(
                    "Aborting TurtleBot4 Navigation system, no URID provided"
                )
                return
            else:
                logging.info(f"TurtleBot4 Navigation system is using URID: {URID}")

            try:
                self.session = zenoh.open(zenoh.Config())
                logging.info(f"Zenoh navigation provider opened {self.session}")
                logging.info(
                    f"TurtleBot4 navigation listeners starting with URID: {URID}"
                )
                self.session.declare_subscriber(f"{URID}/c3/odom", listenerOdom)
            except Exception as e:
                logging.error(f"Error opening Zenoh client: {e}")
        elif not self.use_zenoh:
            # we are using CycloneDDS e.g. for the Unitree Go2
            try:
                self.pose_subscriber = ChannelSubscriber(
                    "rt/utlidar/robot_pose", PoseStamped_
                )
                self.pose_subscriber.Init(self.poseMessageHandler, 10)
            except Exception as e:
                logging.error(f"Error opening CycloneDDS client: {e}")

        self.body_height_cm = 0
        self.body_attitude = None

        self.moving = None
        self.previous_x = 0
        self.previous_y = 0
        self.previous_z = 0
        self.move_history = 0

        self._odom: Optional[dict] = None

        self.x = 0.0
        self.y = 0.0
        self.z = 0.0

        self.yaw_odom_0_360 = 0.0
        self.yaw_odom_m180_p180 = 0.0

        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.start()

    def euler_from_quaternion(self, x, y, z, w):
        """
        https://automaticaddison.com/how-to-convert-a-quaternion-into-euler-angles-in-python/
        Convert a quaternion into euler angles (roll, pitch, yaw)
        roll is rotation around x in radians (counterclockwise)
        pitch is rotation around y in radians (counterclockwise)
        yaw is rotation around z in radians (counterclockwise)
        """
        t0 = +2.0 * (w * x + y * z)
        t1 = +1.0 - 2.0 * (x * x + y * y)
        roll_x = math.atan2(t0, t1)

        t2 = +2.0 * (w * y - z * x)
        t2 = +1.0 if t2 > +1.0 else t2
        t2 = -1.0 if t2 < -1.0 else t2
        pitch_y = math.asin(t2)

        t3 = +2.0 * (w * z + x * y)
        t4 = +1.0 - 2.0 * (y * y + z * z)
        yaw_z = math.atan2(t3, t4)

        return roll_x, pitch_y, yaw_z  # in radians

    def processOdom(self, pose):

        logging.debug(f"pose: {pose}")

        x = pose.orientation.x
        y = pose.orientation.y
        z = pose.orientation.z
        w = pose.orientation.w

        dx = (pose.position.x - self.previous_x) ** 2
        dy = (pose.position.y - self.previous_y) ** 2
        dz = (pose.position.z - self.previous_z) ** 2

        self.previous_x = pose.position.x
        self.previous_y = pose.position.y
        self.previous_z = pose.position.z

        delta = math.sqrt(dx + dy + dz)

        # moving? Use a decay kernal
        self.move_history = 0.4 * delta + 0.6 * self.move_history

        if delta > 0.01 or self.move_history > 0.005:
            # we want to detect movement quickly (and flip "moving" False->True), but
            # wait for the platform to stabilize before we flip "moving" True->False
            self.moving = True
            logging.info(f"delta moving: {delta} {self.move_history}")
        else:
            self.moving = False

        angles = self.euler_from_quaternion(x, y, z, w)

        self.m180_p180 = angles[2] * rad_to_deg * -1.0
        # the * -1.0 changes the heading to sane convention
        # turn right (CW) to INCREASE your heading
        # runs from -180 to + 180, where 0 is the "nose" of the robot

        # runs from 0 to 360
        self.yaw_odom_0_360 = self.m180_p180 + 180.0

        # current position in world frame
        self.x = pose.position.x
        self.y = pose.position.y

        self._odom = {
            "x": self.x,
            "y": self.y,
            "yaw_odom_0_360": self.yaw_odom_0_360,
            "yaw_odom_m180_p180": self.m180_p180,
            "body_height_cm": self.body_height_cm,
            "body_attitude": self.body_attitude,
            "moving": self.moving,
        }

        logging.debug(
            (
                f"NAV x,y,yaw_odom,yaw_mag,moving:{round(self.x,2)},{round(self.y,2)},",
                f"{round(self.yaw_odom_0_360,2)},{self.moving})",
            )
        )

    def poseMessageHandler(self, msg):
        # used by CycloneDDS / Unitree Go2

        p = msg.pose
        self.body_height_cm = round(p.position.z * 100.0)

        # only relevant to dog
        if self.body_height_cm > 24:
            self.body_attitude = "standing"
        elif self.body_height_cm > 3:
            self.body_attitude = "sitting"

        self.processOdom(p)

    def zenohOdomProcessor(self):
        # used by Zenoh / TurtleBot4

        global gOdom
        if gOdom is None:
            return

        p = gOdom.pose.pose
        self.body_height_cm = 0.0
        self.body_attitude = None
        self.processOdom(p)

    def start(self):
        """
        Starts the Odom Provider and processing thread
        if not already running.
        """
        if self._thread and self._thread.is_alive():
            return

        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        """
        Main loop for the Odom provider.
        """
        while self.running:

            if self.use_zenoh:
                # TurtleBot4, use Zenoh
                logging.debug("zenohOdomProcessor")
                self.zenohOdomProcessor()
            else:
                # Unitree Go2, use CycloneDDS
                logging.debug(
                    f"Cyclone Nav Provider: {self.body_height_cm} position: {self.odom}"
                )

            time.sleep(0.1)

    def stop(self):
        """
        Stop the Odom provider.
        """
        self.running = False
        if self._thread:
            logging.info("Stopping Odom provider")
            self._thread.join(timeout=5)

    @property
    def odom(self) -> Optional[dict]:
        # """
        # Get the current robot odom
        # """
        return self._odom
