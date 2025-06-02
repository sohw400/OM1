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

        self.angle_to_dock = 0.0
        self.distance_to_dock = 0.0

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

        self.angle_to_dock = self.get_angle_to_dock()
        self.distance_to_dock = self.get_distance_to_dock()

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

        front_ranges = np.concatenate([corrected_ranges[90:0], corrected_ranges[-90:]])
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
        degrees_per_reading = 360.0 / num_ranges

        best_angle = None
        best_score = 0
        min_clearance = 0.8

        # Check left side: 0° to 90° in 10° segments
        for i in range(3):  # 9 segments of 10° each
            start_deg = i * 10
            end_deg = (i + 1) * 10
            center_angle = -(start_deg + end_deg) / 2.0

            # Convert to indices
            start_idx = int(-end_deg / degrees_per_reading) % num_ranges
            end_idx = int(-start_deg / degrees_per_reading) % num_ranges

            if start_idx <= end_idx:
                segment_ranges = corrected_ranges[start_idx : end_idx + 1]
            else:
                segment_ranges = np.concatenate(
                    [corrected_ranges[start_idx:], corrected_ranges[: end_idx + 1]]
                )

            valid_ranges = segment_ranges[
                np.isfinite(segment_ranges) & (segment_ranges > 0.1)
            ]

            if len(valid_ranges) > 0:
                min_dist = np.min(valid_ranges)
                clear_pct = np.sum(valid_ranges >= min_clearance) / len(valid_ranges)
                score = min_dist * clear_pct

                if score > best_score and min_dist >= min_clearance * 0.7:
                    best_score = score
                    best_angle = center_angle
                    print(
                        f"Left {start_deg}-{end_deg}°: min={min_dist:.2f}m, clear={clear_pct:.1%}, score={score:.3f}"
                    )

        # Check right side: 0° to 90° in 10° segments
        for i in range(3):  # 9 segments of 10° each
            start_deg = i * 10
            end_deg = (i + 1) * 10
            center_angle = (start_deg + end_deg) / 2.0

            # Convert to indices
            start_idx = int(start_deg / degrees_per_reading)
            end_idx = int(end_deg / degrees_per_reading)

            segment_ranges = corrected_ranges[start_idx : end_idx + 1]
            valid_ranges = segment_ranges[
                np.isfinite(segment_ranges) & (segment_ranges > 0.1)
            ]

            if len(valid_ranges) > 0:
                min_dist = np.min(valid_ranges)
                clear_pct = np.sum(valid_ranges >= min_clearance) / len(valid_ranges)
                score = min_dist * clear_pct

                if score > best_score and min_dist >= min_clearance * 0.7:
                    best_score = score
                    best_angle = center_angle
                    print(
                        f"Right {start_deg}-{end_deg}°: min={min_dist:.2f}m, clear={clear_pct:.1%}, score={score:.3f}"
                    )

        if best_angle is not None:
            target_yaw = self.current_pose["yaw_odom_m180_p180"] + best_angle
            if target_yaw < -180:
                target_yaw += 360
            elif target_yaw > 180:
                target_yaw -= 360

            print(
                f"Best avoidance angle: {best_angle:.2f}° -> Target yaw: {target_yaw:.2f}°"
            )
            return target_yaw
        else:
            return -1

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

            while abs(self.angle_to_dock) > 0.1:
                print(
                    f"Adjusting angle to dock: {self.angle_to_dock:.2f} rad, distance: {self.distance_to_dock:.2f} m"
                )
                angular_z = max(-0.5, min(0.5, self.angle_to_dock * 2.0))
                t = geometry_msgs.Twist(
                    linear=geometry_msgs.Vector3(x=0, y=0.0, z=0.0),
                    angular=geometry_msgs.Vector3(x=0.0, y=0.0, z=angular_z),
                )
                self.session.put(f"{self.urid}/c3/cmd_vel", t.serialize())
                time.sleep(0.5)

                t = geometry_msgs.Twist(
                    linear=geometry_msgs.Vector3(x=0.1, y=0.0, z=0.0),
                    angular=geometry_msgs.Vector3(x=0.0, y=0.0, z=0.0),
                )
                self.session.put(f"{self.urid}/c3/cmd_vel", t.serialize())
                time.sleep(0.5)

            obstacle_ahead = self.check_obstacles_ahead()
            print(
                f"Distance to dock: {self.distance_to_dock:.2f}, Angle to dock: {self.angle_to_dock:.2f}"
            )
            if obstacle_ahead and self.distance_to_dock > 0.2:
                target_yaw = self.avoid_obstacles()
                if target_yaw is not None:
                    if target_yaw == -1:
                        print("No valid avoidance angle found, stopping.")
                        t = geometry_msgs.Twist(
                            linear=geometry_msgs.Vector3(x=-0.5, y=0.0, z=0.0),
                            angular=geometry_msgs.Vector3(x=0.0, y=0.0, z=0.0),
                        )
                        self.session.put(f"{self.urid}/c3/cmd_vel", t.serialize())
                        continue

                    while abs(target_yaw - self.current_pose["yaw_odom_m180_p180"]) > 5:
                        gap = target_yaw - self.current_pose["yaw_odom_m180_p180"]
                        if gap > 180:
                            gap -= 360
                        elif gap < -180:
                            gap += 360
                        turning_direction = 0.5 if gap < 0 else -0.5
                        t = geometry_msgs.Twist(
                            linear=geometry_msgs.Vector3(x=0, y=0.0, z=0.0),
                            angular=geometry_msgs.Vector3(
                                x=0.0, y=0.0, z=turning_direction
                            ),
                        )
                        print(
                            f"Avoiding obstacle: turning to {target_yaw:.2f} rad target_yaw {target_yaw} current_yaw {self.current_pose['yaw_odom_m180_p180']}"
                        )
                        self.session.put(f"{self.urid}/c3/cmd_vel", t.serialize())
                        time.sleep(0.5)
            else:
                # if abs(angle_to_dock) > 0.2:
                #     angular_z = max(-0.5, min(0.5, angle_to_dock * 2.0))
                #     t = geometry_msgs.Twist(
                #         linear=geometry_msgs.Vector3(x=0, y=0.0, z=0.0),
                #         angular=geometry_msgs.Vector3(x=0.0, y=0.0, z=angular_z),
                #     )
                # else:
                t = geometry_msgs.Twist(
                    linear=geometry_msgs.Vector3(
                        x=min(0.3, self.distance_to_dock * 0.5), y=0.0, z=0.0
                    ),
                    angular=geometry_msgs.Vector3(x=0.0, y=0.0, z=0),
                )
                print(
                    f"Moving towards dock: distance={self.distance_to_dock:.2f}, angle={self.angle_to_dock:.2f}"
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

    # target_yaw = auto_charge.avoid_obstacles()
    # if target_yaw is not None:
    #     while abs(target_yaw - auto_charge.current_pose["yaw_odom_m180_p180"]) > 5:
    #         gap = target_yaw - auto_charge.current_pose["yaw_odom_m180_p180"]
    #         if gap > 180:
    #             gap -= 360
    #         elif gap < -180:
    #             gap += 360
    #         turning_direction = 0.5 if gap < 0 else -0.5
    #         t = geometry_msgs.Twist(
    #             linear=geometry_msgs.Vector3(x=0, y=0.0, z=0.0),
    #             angular=geometry_msgs.Vector3(
    #                 x=0.0, y=0.0, z=turning_direction
    #             ),
    #         )
    #         print(f"Avoiding obstacle: turning to {target_yaw:.2f} rad target_yaw {target_yaw} current_yaw {auto_charge.current_pose['yaw_odom_m180_p180']}")
    #         auto_charge.session.put(f"{auto_charge.urid}/c3/cmd_vel", t.serialize())
    #         time.sleep(0.5)

    auto_charge.start_navigation_to_dock()

    while True:
        time.sleep(1)
