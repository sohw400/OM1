import argparse
import math
import time

import numpy as np
import zenoh

from zenoh_idl import geometry_msgs, nav_msgs, sensor_msgs

parser = argparse.ArgumentParser()
parser.add_argument("--URID", help="your robot's URID, when using Zenoh", type=str)
print(parser.format_help())

args = parser.parse_args()

rad_to_deg = 57.2958


class AutoCharge:
    def __init__(self, urid):
        self.urid = urid
        self.session = zenoh.open(zenoh.Config())
        print(f"Zenoh session opened: {self.session} for URID: {self.urid}")
        self.scan_subscriber = self.session.declare_subscriber(
            f"{self.urid}/pi/scan", self.listen_scan
        )
        self.odom_subscriber = self.session.declare_subscriber(
            f"{self.urid}/c3/odom", self.listen_odom
        )
        self.docker_status_subscriber = self.session.declare_subscriber(
            f"{self.urid}/c3/dock_status", self.listen_docker_status
        )

        self.scan_data = None
        self.is_docked = False

        self.docker_position = None
        self.current_pose = None

    def listen_odom(self, data: zenoh.Sample):
        odom_data = nav_msgs.Odometry.deserialize(data.payload.to_bytes())
        position = odom_data.pose.pose.position
        orientation = odom_data.pose.pose.orientation

        angles = self.euler_from_quaternion(
            orientation.x, orientation.y, orientation.z, orientation.w
        )

        self.current_pose = {
            "x": position.x,
            "y": position.y,
            "z": position.z,
            "yaw": angles[2],
            "yaw_odom_m180_p180": angles[2] * rad_to_deg * -1.0,
            "yaw_odom_0_360": angles[2] * rad_to_deg * -1.0 + 180.0,
        }

        if self.is_docked:
            print(
                f"Robot is docked, saving current pose as docker position. {self.current_pose}"
            )
            self.docker_position = self.current_pose

    def listen_scan(self, data: zenoh.Sample):
        self.scan_data = sensor_msgs.LaserScan.deserialize(data.payload.to_bytes())

    def listen_docker_status(self, data: zenoh.Sample):
        docker_status = sensor_msgs.DockStatus.deserialize(data.payload.to_bytes())
        if docker_status.is_docked:
            self.is_docked = True

    def check_obstacles_ahead(self) -> bool:
        if not self.scan_data:
            print("No scan data received yet.")
            return False

        ranges = np.array(self.scan_data.ranges)

        # Rotate 90 degrees to align the front of the robot
        num_ranges = len(ranges)
        shift = num_ranges // 4
        corrected_ranges = np.roll(ranges, -shift)

        front_ranges = np.concatenate([corrected_ranges[:30], corrected_ranges[-30:]])
        front_ranges = front_ranges[np.isfinite(front_ranges) & (front_ranges > 0.1)]

        if len(front_ranges) > 0:
            min_distance = np.min(front_ranges)
            print(f"Front distance: {min_distance:.2f} m")
            return min_distance < 0.5

        return False

    def avoid_obstacles(self):
        if not self.scan_data:
            return None

        ranges = np.array(self.scan_data.ranges)
        num_ranges = len(ranges)
        shift = num_ranges // 4
        corrected_ranges = np.roll(ranges, -shift)

        # Check left and right clearance
        left_ranges = corrected_ranges[45:135]  # Left 90 degrees
        right_ranges = corrected_ranges[225:315]  # Right 90 degrees

        left_clearance = np.mean(
            left_ranges[np.isfinite(left_ranges) & (left_ranges > 0.1)]
        )
        right_clearance = np.mean(
            right_ranges[np.isfinite(right_ranges) & (right_ranges > 0.1)]
        )

        if left_clearance > right_clearance:
            t = geometry_msgs.Twist(
                linear=geometry_msgs.Vector3(x=0.0, y=0.0, z=0.0),
                angular=geometry_msgs.Vector3(x=0.0, y=0.0, z=-0.5),
            )
        else:
            t = geometry_msgs.Twist(
                linear=geometry_msgs.Vector3(x=0.0, y=0.0, z=0.0),
                angular=geometry_msgs.Vector3(x=0.0, y=0.0, z=0.5),
            )

        return t

    def get_distance_to_dock(self):
        if not self.current_pose or not self.docker_position:
            return float("inf")

        dx = self.docker_position["x"] - self.current_pose["x"]
        dy = self.docker_position["y"] - self.current_pose["y"]
        return math.sqrt(dx * dx + dy * dy)

    def get_angle_to_dock(self):
        if not self.current_pose or not self.docker_position:
            return 0.0

        dx = self.docker_position["x"] - self.current_pose["x"]
        dy = self.docker_position["y"] - self.current_pose["y"]

        # Angle to target in global frame
        target_angle = math.atan2(dy, dx)

        # Relative angle (difference from current heading)
        angle_diff = target_angle - self.current_pose["yaw"]

        # Normalize to [-pi, pi]
        while angle_diff > math.pi:
            angle_diff -= 2 * math.pi
        while angle_diff < -math.pi:
            angle_diff += 2 * math.pi

        return angle_diff

    def start_navigation_to_dock(self):
        if not self.current_pose:
            print("Current pose not available. Cannot navigate to dock.")
            return

        while self.is_docked is False:

            if not self.docker_position:
                print("Set docker position to 0, 0, 0 by default.")
                self.docker_position = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0}

            distance = self.get_distance_to_dock()
            angle_to_dock = self.get_angle_to_dock()

            obstacle_ahead = self.check_obstacles_ahead()
            print(
                f"Distance to dock: {distance:.2f}, Angle to dock: {angle_to_dock:.2f}"
            )
            if obstacle_ahead and distance > 0.2:
                t = self.avoid_obstacles()
                if t:
                    print("Obstacle detected, avoiding...")
                    self.session.put(f"{self.urid}/c3/cmd_vel", t.serialize())
            else:
                if abs(angle_to_dock) > 0.2:
                    angular_z = 0.5 if angle_to_dock > 0 else -0.5
                    t = geometry_msgs.Twist(
                        linear=geometry_msgs.Vector3(x=0, y=0.0, z=0.0),
                        angular=geometry_msgs.Vector3(x=0.0, y=0.0, z=angular_z),
                    )
                else:
                    t = geometry_msgs.Twist(
                        linear=geometry_msgs.Vector3(
                            x=min(0.3, distance * 0.2), y=0.0, z=0.0
                        ),
                        angular=geometry_msgs.Vector3(
                            x=0.0, y=0.0, z=angle_to_dock * 0.1
                        ),
                    )
                print(
                    f"Moving towards dock: distance={distance:.2f}, angle={angle_to_dock:.2f}"
                )
                self.session.put(f"{self.urid}/c3/cmd_vel", t.serialize())

            print(
                f"Current pose: {self.current_pose}, Docker position: {self.docker_position}"
            )
            time.sleep(0.1)

    def euler_from_quaternion(self, x: float, y: float, z: float, w: float) -> tuple:
        """
        https://automaticaddison.com/how-to-convert-a-quaternion-into-euler-angles-in-python/
        Convert a quaternion into euler angles (roll, pitch, yaw)
        roll is rotation around x in radians (counterclockwise)
        pitch is rotation around y in radians (counterclockwise)
        yaw is rotation around z in radians (counterclockwise)

        Parameters
        ----------
        x : float
            The x component of the quaternion.
        y : float
            The y component of the quaternion.
        z : float
            The z component of the quaternion.
        w : float
            The w component of the quaternion.

        Returns
        -------
        tuple
            A tuple containing the roll, pitch, and yaw angles in radians.
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


if __name__ == "__main__":

    URID = args.URID
    print(f"Using Zenoh to connect to robot using {URID}")
    print("[INFO] Opening zenoh session...")

    auto_charge = AutoCharge(URID)

    while auto_charge.current_pose is None:
        print("Waiting for odometry data...")
        time.sleep(0.5)

    auto_charge.start_navigation_to_dock()

    while True:
        time.sleep(1)
