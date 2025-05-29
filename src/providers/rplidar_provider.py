import logging
import math
import threading
import time
from typing import Optional

import bezier
import numpy as np
import zenoh
from numpy.typing import NDArray

from zenoh_idl import sensor_msgs

from .rplidar_driver import RPDriver
from .singleton import singleton

gScan = None


def listenerScan(sample):
    global gScan
    gScan = sensor_msgs.LaserScan.deserialize(sample.payload.to_bytes())
    # logging.debug(f"Zenoh Laserscan data: {gScan}")


def get_dimensions(list_):
    if not isinstance(list_, list):
        return []
    return [len(list_)] + get_dimensions(list_[0]) if list_ else [0]


@singleton
class RPLidarProvider:
    """
    RPLidar Provider.

    This class implements a singleton pattern to manage RPLidar data streaming.

    Parameters
    ----------
    serial_port: str = "/dev/cu.usbserial-0001"
        The name of the serial port in use by the RPLidar sensor.
    half_width_robot: float = 0.20
        The half width of the robot in m
    angles_blanked: list = []
        Regions of the scan to disregard, runs from -180 to +180 deg
    max_relevant_distance: float = 1.1
        Only consider barriers within this range, in m
    sensor_mounting_angle: float = 180.0
        The angle of the sensor zero relative to the way in which it's mounted
    """

    def __init__(
        self,
        serial_port: str = "/dev/cu.usbserial-0001",
        half_width_robot: float = 0.20,
        angles_blanked: list = [],
        max_relevant_distance: float = 1.1,
        sensor_mounting_angle: float = 180.0,
        URID: str = "",
        use_zenoh: bool = False,
        simple_paths: bool = False,
    ):
        """
        Robot and sensor configuration
        """

        logging.info("Booting RPLidar")

        self.serial_port = serial_port
        self.half_width_robot = half_width_robot
        self.angles_blanked = angles_blanked
        self.max_relevant_distance = max_relevant_distance
        self.sensor_mounting_angle = sensor_mounting_angle
        self.URID = URID
        self.use_zenoh = use_zenoh
        self.simple_paths = simple_paths

        self.running: bool = False
        self.lidar = None
        self.zen = None
        self.scans = None

        self._raw_scan: Optional[NDArray] = None
        self._valid_paths: Optional[list] = None
        self._lidar_string: str = None

        self.angles = None
        self.angles_final = None
        
        # Initialize path planning components
        self._init_path_planning()

        # logging.info(self.paths)
        # logging.info(self.pp)

        self._thread: Optional[threading.Thread] = None

        if not self.use_zenoh:
            try:
                self.lidar = RPDriver(self.serial_port)

                info = self.lidar.get_info()
                ret = f"RPLidar Info: {info}"

                logging.info(ret)

                health = self.lidar.get_health()
                ret = f"RPLidar Health: {health[0]}"
                logging.info(ret)

                if health[0] == "Good":
                    logging.info(ret)
                else:
                    logging.info(f"there is a problem with the LIDAR: {ret}")

                # reset to clear buffers
                self.lidar.reset()

                time.sleep(0.5)

            except Exception as e:
                logging.error(f"Error in RPLidar provider: {e}")

        elif self.use_zenoh:
            logging.info("Connecting to the RPLIDAR via Zenoh")
            try:
                self.zen = zenoh.open(zenoh.Config())
                logging.info(f"Zenoh move client opened {self.zen}")
                logging.info(
                    f"TurtleBot4 RPLIDAR listener starting with URID: {self.URID}"
                )
                self.zen.declare_subscriber(f"{self.URID}/pi/scan", listenerScan)
            except Exception as e:
                logging.error(f"Error opening Zenoh client: {e}")

    def start(self):
        """
        Starts the RPLidar and processing thread
        if not already running.
        """
        if self._thread and self._thread.is_alive():
            return

        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _preprocess_zenoh(self, scan):

        if scan is None:
            logging.info("Waiting for Zenoh Laserscan data...")
            self._raw_scan = []
            self._lidar_string = "You might be surrounded by objects and cannot safely move in any direction. DO NOT MOVE."
            self._valid_paths = []
        else:
            # logging.debug(f"_preprocess_zenoh: {scan}")
            # angle_min=-3.1241390705108643, angle_max=3.1415927410125732

            if not self.angles:
                self.angles = list(
                    map(
                        lambda x: 360.0 * (x + math.pi) / (2 * math.pi),
                        np.arange(scan.angle_min, scan.angle_max, scan.angle_increment),
                    )
                )
                self.angles_final = np.flip(self.angles)

            # angles now run from 360.0 to 0 degress
            data = list(zip(self.angles_final, scan.ranges))
            array_ready = np.array(data)
            # print(f"Array {array_ready}")
            self._process(array_ready)

    def _preprocess_serial(self, scan):
        logging.debug(f"_preprocess_serial: {scan}")
        array = np.array(scan)

        # logging.info(f"_preprocess_serial: {array.ndim}")

        # the driver sends angles in degrees between from 0 to 360
        # warning - the driver may send two or more readings per angle,
        # this can be confusing for the code
        angles = array[:, 0]

        # logging.info(f"_preprocess_serial: {angles}")

        # distances are in millimeters
        distances_m = array[:, 1] / 1000

        data = list(zip(angles, distances_m))

        # logging.info(f"_preprocess_serial: {data}")
        array_ready = np.array(data)
        # print(f"Array {array_ready}")
        self._process(array_ready)

    def _init_path_planning(self):
        """Initialize Bezier curves and path planning data structures."""
        self.curves = [
            bezier.Curve(
                np.asfortranarray([[0.0, -0.3, -0.75], [0.0, 0.5, 0.40]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, -0.3, -0.70], [0.0, 0.6, 0.70]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, -0.2, -0.60], [0.0, 0.7, 0.90]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, -0.1, -0.35], [0.0, 0.7, 1.03]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, 0.0, 0.00], [0.0, 0.5, 1.05]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, +0.1, +0.35], [0.0, 0.7, 1.03]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, +0.2, +0.60], [0.0, 0.7, 0.90]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, +0.3, +0.70], [0.0, 0.6, 0.70]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, +0.3, +0.75], [0.0, 0.5, 0.40]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, 0.0, 0.00], [0.0, -0.5, -1.05]]), degree=2
            ),
        ]

        self.paths = []
        self.pp = []
        self.s_vals = np.linspace(0.0, 1.0, 10)

        for curve in self.curves:
            cp = curve.evaluate_multi(self.s_vals)
            self.paths.append(cp)
            pairs = list(zip(cp[0], cp[1]))
            self.pp.append(pairs)

    def _transform_coordinates(self, data):
        """Transform raw lidar data to robot coordinate system."""
        complexes = []

        for angle, distance in data:
            d_m = distance

            # Don't worry about distant objects
            if d_m > self.max_relevant_distance:
                continue

            # Correctly orient the sensor zero to the robot zero
            angle = angle + self.sensor_mounting_angle
            if angle >= 360.0:
                angle = angle - 360.0
            elif angle < 0.0:
                angle = 360.0 + angle

            # Convert the angle from [0 to 360] to [-180 to +180] range
            angle = angle - 180.0

            # Check for blanked angles (robot reflections)
            reflection = False
            for b in self.angles_blanked:
                if angle >= b[0] and angle <= b[1]:
                    reflection = True
                    break

            if reflection:
                continue

            # Convert to cartesian coordinates
            a_rad = (angle + 180.0) * math.pi / 180.0
            v1 = d_m * math.cos(a_rad)
            v2 = d_m * math.sin(a_rad)

            # Convert to x and y (x: backwards to forwards, y: left to right)
            x = -1 * v2
            y = -1 * v1

            complexes.append([x, y, angle, d_m])

        return np.array(complexes)

    def _categorize_paths(self, possible_paths):
        """Categorize valid paths into movement directions."""
        turn_left = []
        advance = []
        turn_right = []
        retreat = []

        ppl = possible_paths.tolist()
        for p in ppl:
            if p < 4:
                turn_left.append(p)
            elif p == 4:
                advance.append(p)
            elif p < 9:
                turn_right.append(p)
            elif p == 9:
                retreat.append(p)

        return turn_left, advance, turn_right, retreat, ppl

    def _generate_movement_string(self, turn_left, advance, turn_right, retreat, ppl):
        """Generate natural language description of safe movements."""
        if len(ppl) == 0:
            return "You are surrounded by objects and cannot safely move in any direction. DO NOT MOVE."

        return_string = "The safe movement directions are: {"
        if self.use_zenoh:  # TurtleBot4
            if len(advance) > 0:
                return_string += "'turn left', 'turn right', 'move forwards', "
            else:
                return_string += "'turn left', 'turn right', "
        else:
            if len(turn_left) > 0:
                return_string += "'turn left', "
            if len(advance) > 0:
                return_string += "'move forwards', "
            if len(turn_right) > 0:
                return_string += "'turn right', "
            if len(retreat) > 0:
                return_string += "'move back', "
        return_string += "'stand still'}. "
        return return_string

    def _process(self, data):
        """Process lidar data and determine safe movement paths."""
        # Transform raw data to robot coordinates
        array = self._transform_coordinates(data)

        # Determine possible paths
        possible_paths = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
        if self.simple_paths:
            possible_paths = np.array([4])  # TurtleBot4 can only advance

        if array.ndim > 1:
            # Sort by angle to handle sensor timing issues
            sorted_indices = array[:, 2].argsort()
            array = array[sorted_indices]

            X = array[:, 0]
            Y = array[:, 1]
            D = array[:, 3]

            # Check path collisions
            for x, y, d in list(zip(X, Y, D)):
                for apath in possible_paths:
                    for point in self.pp[apath]:
                        p1 = x - point[0]
                        p2 = y - point[1]
                        dist = math.sqrt(p1 * p1 + p2 * p2)
                        if dist < self.half_width_robot:
                            logging.debug(f"removing path: {apath}")
                            path_to_remove = np.array([apath])
                            possible_paths = np.setdiff1d(
                                possible_paths, path_to_remove
                            )
                            break

        # Categorize and generate output
        turn_left, advance, turn_right, retreat, ppl = self._categorize_paths(possible_paths)
        return_string = self._generate_movement_string(turn_left, advance, turn_right, retreat, ppl)

        self._raw_scan = array
        self._lidar_string = return_string
        self._valid_paths = ppl

        logging.debug(
            f"RPLidar Provider string: {self._lidar_string}\nValid paths: {self._valid_paths}"
        )

    def _run(self):
        """
        Main loop for the RPLidar provider.

        Continuously processes RPLidar data and send them
        to the inputs and actions, as needed.
        """
        while self.running:
            if self.use_zenoh:
                global gScan
                logging.debug(f"Zenoh: {gScan}")
                self._preprocess_zenoh(gScan)
                time.sleep(0.1)
            else:
                # we are using serial
                try:
                    for i, scan in enumerate(
                        self.lidar.iter_scans_local(
                            scan_type="express",
                            max_buf_meas=0,
                            min_len=25,
                            max_distance_mm=1500,
                        )
                    ):
                        self._preprocess_serial(scan)
                        time.sleep(0.05)
                except Exception as e:
                    logging.error(f"Error in Serial RPLidar provider: {e}")

    def stop(self):
        """
        Stop the RPLidar provider.
        """
        self.running = False
        if self._thread:
            logging.info("Stopping RPLidar provider")
            if not self.use_zenoh:
                self.lidar.stop()
                self.lidar.disconnect()
                time.sleep(0.5)
            self._thread.join(timeout=5)

    @property
    def valid_paths(self) -> Optional[list]:
        """
        Get the currently valid paths.

        Returns
        -------
        Optional[list]
            The currently valid paths as a list, or None if not
            available. The list contains 0 to 10 entries,
            corresponding to possible paths - for example: [0,3,4,5]
        """
        return self._valid_paths

    @property
    def raw_scan(self) -> Optional[NDArray]:
        """
        Get the latest raw scan data.

        Returns
        -------
        Optional[NDArray]
            The latest raw scan result as a NumPy array, or None if not
            available.
        """
        return self._raw_scan

    @property
    def lidar_string(self) -> str:
        """
        Get the latest natural language assessment of possible paths.

        Returns
        -------
        str
            A natural language summary of possible motion paths
        """
        return self._lidar_string
    
    @staticmethod
    def categorize_paths_static(possible_paths):
        """Static method to categorize paths - for use by other modules."""
        turn_left = []
        advance = []
        turn_right = []
        retreat = []

        ppl = possible_paths.tolist() if hasattr(possible_paths, 'tolist') else possible_paths
        for p in ppl:
            if p < 4:
                turn_left.append(p)
            elif p == 4:
                advance.append(p)
            elif p < 9:
                turn_right.append(p)
            elif p == 9:
                retreat.append(p)

        return turn_left, advance, turn_right, retreat, ppl
    
    @staticmethod
    def get_bezier_curves():
        """Get the standard Bezier curves for path planning."""
        import bezier
        import numpy as np
        
        curves = [
            bezier.Curve(
                np.asfortranarray([[0.0, -0.3, -0.75], [0.0, 0.5, 0.40]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, -0.3, -0.70], [0.0, 0.6, 0.70]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, -0.2, -0.60], [0.0, 0.7, 0.90]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, -0.1, -0.35], [0.0, 0.7, 1.03]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, 0.0, 0.00], [0.0, 0.5, 1.05]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, +0.1, +0.35], [0.0, 0.7, 1.03]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, +0.2, +0.60], [0.0, 0.7, 0.90]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, +0.3, +0.70], [0.0, 0.6, 0.70]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, +0.3, +0.75], [0.0, 0.5, 0.40]]), degree=2
            ),
            bezier.Curve(
                np.asfortranarray([[0.0, 0.0, 0.00], [0.0, -0.5, -1.05]]), degree=2
            ),
        ]
        return curves
    
    @staticmethod
    def compute_path_points(curves=None):
        """Compute path points from Bezier curves."""
        import numpy as np
        
        if curves is None:
            curves = RPLidarProvider.get_bezier_curves()
            
        paths = []
        pp = []
        s_vals = np.linspace(0.0, 1.0, 10)

        for curve in curves:
            cp = curve.evaluate_multi(s_vals)
            paths.append(cp)
            pairs = list(zip(cp[0], cp[1]))
            pp.append(pairs)
            
        return paths, pp
    
    @staticmethod
    def transform_coordinates_static(data, max_relevant_distance, sensor_mounting_angle, angles_blanked):
        """Static method to transform lidar coordinates - for use by other modules."""
        import math
        import numpy as np
        
        complexes = []

        for angle, distance in data:
            d_m = distance

            # Don't worry about distant objects
            if d_m > max_relevant_distance:
                continue

            # Correctly orient the sensor zero to the robot zero
            angle = angle + sensor_mounting_angle
            if angle >= 360.0:
                angle = angle - 360.0
            elif angle < 0.0:
                angle = 360.0 + angle

            # Convert the angle from [0 to 360] to [-180 to +180] range
            angle = angle - 180.0

            # Check for blanked angles (robot reflections)
            reflection = False
            for b in angles_blanked:
                if angle >= b[0] and angle <= b[1]:
                    reflection = True
                    break

            if reflection:
                continue

            # Convert to cartesian coordinates
            a_rad = (angle + 180.0) * math.pi / 180.0
            v1 = d_m * math.cos(a_rad)
            v2 = d_m * math.sin(a_rad)

            # Convert to x and y (x: backwards to forwards, y: left to right)
            x = -1 * v2
            y = -1 * v1

            complexes.append([x, y, angle, d_m])

        return np.array(complexes)
    
    @staticmethod
    def validate_movement_direction(direction_paths, min_paths=1):
        """Validate if a movement direction has enough valid paths."""
        return len(direction_paths) >= min_paths
    
    @staticmethod
    def get_movement_safety_check(turn_left, advance, turn_right, retreat, direction, min_paths=1):
        """Check if a specific movement direction is safe."""
        if direction == "turn left":
            return RPLidarProvider.validate_movement_direction(turn_left, min_paths)
        elif direction == "turn right":
            return RPLidarProvider.validate_movement_direction(turn_right, min_paths)
        elif direction == "advance" or direction == "move forwards":
            return RPLidarProvider.validate_movement_direction(advance, min_paths)
        elif direction == "retreat" or direction == "move back":
            return RPLidarProvider.validate_movement_direction(retreat, min_paths)
        return False
EOF < /dev/null