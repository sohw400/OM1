import logging
import math
import random
import time
from queue import Queue
from typing import List, Optional

import zenoh

from actions.base import ActionConfig, ActionConnector, MoveCommand
from actions.move_go2_autonomy.interface import MoveInput
from providers.face_presence_provider import FacePresenceProvider
from providers.odom_provider import OdomProvider, RobotState
from providers.simple_paths_provider import SimplePathsProvider
from providers.unitree_go2_state_provider import UnitreeGo2StateProvider
from unitree.unitree_sdk2py.go2.sport.sport_client import SportClient
from zenoh_msgs import (
    AIStatusRequest,
    AIStatusResponse,
    String,
    open_zenoh_session,
    prepare_header,
)


class MoveUnitreeSDKAdvanceConnector(ActionConnector[MoveInput]):

    def __init__(self, config: ActionConfig):
        super().__init__(config)

        self.dog_attitude = None

        # Movement parameters
        self.move_speed = 0.5
        self.turn_speed = 0.8
        self.angle_tolerance = 5.0  # degrees
        self.distance_tolerance = 0.05  # meters
        self.pending_movements: Queue[Optional[MoveCommand]] = Queue()
        self.movement_attempts = 0
        self.movement_attempt_limit = 15
        self.gap_previous = 0

        self.path_provider = SimplePathsProvider()
        self.unitree_go2_state = UnitreeGo2StateProvider()
        self.face_presence_provider = FacePresenceProvider()

        # create sport client
        self.sport_client = None
        try:
            self.sport_client = SportClient()
            self.sport_client.SetTimeout(10.0)
            self.sport_client.Init()
            self.sport_client.StopMove()
            self.sport_client.Move(0.05, 0, 0)
            logging.info("Autonomy Unitree sport client initialized")
        except Exception as e:
            logging.error(f"Error initializing Unitree sport client: {e}")

        unitree_ethernet = getattr(config, "unitree_ethernet", None)
        if unitree_ethernet is None:
            raise ValueError("unitree_ethernet must be specified in the config")
        self.odom = OdomProvider(channel=unitree_ethernet)

        # Zenoh topic for AI control status
        self.ai_status_request = "om/ai/request"
        self.ai_status_response = "om/ai/response"
        self.session: Optional[zenoh.Session] = None
        self.pub = None

        try:
            self.session = open_zenoh_session()
            self.session.declare_subscriber(
                self.ai_status_request, self._zenoh_ai_status_request
            )
            self._zenoh_ai_status_response_pub = self.session.declare_publisher(
                self.ai_status_response
            )
        except Exception as e:
            logging.error(f"Error opening Zenoh client: {e}")
            self.session = None
            self.pub = None

        # AI control status
        self.ai_control_enabled = True

        # Mode
        self.mode = getattr(self.config, "mode", None)

        logging.info(f"Autonomy Odom Provider: {self.odom}")

    async def connect(self, output_interface: MoveInput) -> None:
        logging.info(f"AI command.connect: {output_interface.action}")

        if self.mode == "guard" and self.face_presence_provider.unknown_faces > 0:
            logging.info(
                "Guard mode active and unknown face detected - disregarding AI command"
            )
            return

        if not self.ai_control_enabled:
            logging.info("AI Control is disabled - disregarding AI command")
            return

        if self.unitree_go2_state.state_code == 1002:
            if self.sport_client:
                logging.info("Robot is in jointLock state - issuing BalanceStand()")
                self.sport_client.BalanceStand()

        if self.unitree_go2_state.action_progress != 0:
            logging.info(
                f"Action in progress: {self.unitree_go2_state.action_progress}"
            )
            return

        # fallback to the odom provider
        if not self.unitree_go2_state.state_code:
            if self.odom.position["moving"]:
                # for example due to a teleops or game controller command
                logging.info(
                    "Disregard new AI movement command - robot is already moving"
                )
                return

        if self.pending_movements.qsize() > 0:
            logging.info("Movement in progress: disregarding new AI command")
            return

        if self.odom.position["odom_x"] == 0.0:
            # this value is never precisely zero EXCEPT while
            # booting and waiting for data to arrive
            logging.info("Waiting for location data")
            return

        # Process movement commands with lidar safety checks
        movement_map = {
            "turn left": self._process_turn_left,
            "turn right": self._process_turn_right,
            "move forwards": self._process_move_forward,
            "move back": self._process_move_back,
            "stand still": lambda: logging.info("AI movement command: stand still"),
        }

        handler = movement_map.get(output_interface.action)
        if handler:
            handler()
        else:
            logging.info(f"AI movement command unknown: {output_interface.action}")

        # This is a subset of Go2 movements that are
        # generally safe. Note that the "stretch" action involves
        # about 40 cm of back and forth motion, and the "dance"
        # action involves copious jumping in place for about 10 seconds.

        # if output_interface.action == "stand up":
        #     logging.info("Unitree AI command: stand up")
        #     await self._execute_sport_command("StandUp")
        # elif output_interface.action == "sit":
        #     logging.info("Unitree AI command: lay down")
        #     await self._execute_sport_command("StandDown")
        # elif output_interface.action == "shake paw":
        #     logging.info("Unitree AI command: shake paw")
        #     await self._execute_sport_command("Hello")
        # elif output_interface.action == "stretch":
        #     logging.info("Unitree AI command: stretch")
        #     await self._execute_sport_command("Stretch")
        # elif output_interface.action == "dance":
        #     logging.info("Unitree AI command: dance")
        #     await self._execute_sport_command("Dance1")

    def _move_robot(self, vx: float, vy: float, vturn=0.0) -> None:
        """
        Move the robot with specified velocities.

        Parameters:
        -----------
        vx : float
            Linear velocity in the x direction (m/s).
        vy : float
            Linear velocity in the y direction (m/s).
        vturn : float, optional
            Angular velocity (turning speed) in radians per second (default is 0.0).
        """
        logging.info(f"_move_robot: vx={vx}, vy={vy}, vturn={vturn}")

        if not self.sport_client:
            return

        if self.odom.position["body_attitude"] != RobotState.STANDING:
            return

        if self.unitree_go2_state.state == "jointLock":
            self.sport_client.BalanceStand()

        try:
            logging.info(f"self.sport_client.Move: vx={vx}, vy={vy}, vturn={vturn}")
            self.sport_client.Move(vx, vy, vturn)
        except Exception as e:
            logging.error(f"Error moving robot: {e}")

    def clean_abort(self) -> None:
        """
        Cleanly abort current movement and reset state.
        """
        self.movement_attempts = 0
        if not self.pending_movements.empty():
            self.pending_movements.get()

    def tick(self) -> None:
        """
        Process the AI motion tick.
        """
        logging.debug("AI Motion Tick")

        if self.odom is None:
            logging.info("Waiting for odom data = self.odom is None")
            time.sleep(0.5)
            return

        if self.odom.position["odom_x"] == 0.0:
            # this value is never precisely zero except while
            # booting and waiting for data to arrive
            logging.info("Waiting for odom data, x == 0.0")
            time.sleep(0.5)
            return

        if self.odom.position["body_attitude"] != RobotState.STANDING:
            logging.info("Cannot move - dog is sitting")
            time.sleep(0.5)
            return

        # if we got to this point, we have good data and we are able to
        # safely proceed
        target: List[MoveCommand] = list(self.pending_movements.queue)

        if len(target) > 0:

            current_target = target[0]

            logging.info(
                f"Target: {current_target} current yaw: {self.odom.position['odom_yaw_m180_p180']}"
            )

            if self.movement_attempts > self.movement_attempt_limit:
                # abort - we are not converging
                self.clean_abort()
                logging.info(
                    f"TIMEOUT - not converging after {self.movement_attempt_limit} attempts - StopMove()"
                )
                return

            goal_dx = current_target.dx
            goal_yaw = current_target.yaw

            # Phase 1: Turn to face the target direction
            if not current_target.turn_complete:
                gap = self._calculate_angle_gap(
                    -1 * self.odom.position["odom_yaw_m180_p180"], goal_yaw
                )
                logging.info(f"Phase 1 - Turning remaining GAP: {gap}DEG")

                progress = round(abs(self.gap_previous - gap), 2)
                self.gap_previous = gap
                if self.movement_attempts > 0:
                    logging.info(f"Phase 1 - Turn GAP delta: {progress}DEG")

                if abs(gap) > 10.0:
                    logging.debug("Phase 1 - Gap is big, using large displacements")
                    self.movement_attempts += 1
                    if not self._execute_turn(gap):
                        self.clean_abort()
                        return
                elif abs(gap) > self.angle_tolerance and abs(gap) <= 10.0:
                    logging.debug("Phase 1 - Gap is decreasing, using smaller steps")
                    self.movement_attempts += 1
                    # rotate only because we are so close
                    # no need to check barriers because we are just performing small rotations
                    if gap > 0:
                        self._move_robot(0, 0, 0.2)
                    elif gap < 0:
                        self._move_robot(0, 0, -0.2)
                elif abs(gap) <= self.angle_tolerance:
                    logging.info("Phase 1 - Turn completed, starting movement")
                    current_target.turn_complete = True
                    self.gap_previous = 0

            else:
                # Phase 2: Move towards the target position, if needed
                if goal_dx == 0:
                    logging.info("No movement required, processing next AI command")
                    self.clean_abort()
                    return

                s_x = current_target.start_x
                s_y = current_target.start_y
                speed = current_target.speed

                distance_traveled = math.sqrt(
                    (self.odom.position["odom_x"] - s_x) ** 2
                    + (self.odom.position["odom_y"] - s_y) ** 2
                )
                gap = round(abs(goal_dx - distance_traveled), 2)
                progress = round(abs(self.gap_previous - gap), 2)
                self.gap_previous = gap

                if self.movement_attempts > 0:
                    logging.info(f"Phase 2 - Forward/retreat GAP delta: {progress}m")

                if goal_dx > 0:
                    if 4 not in self.path_provider.advance:
                        logging.warning("Cannot advance due to barrier")
                        self.clean_abort()
                        return
                    fb = 1

                if goal_dx < 0:
                    if not self.path_provider.retreat:
                        logging.warning("Cannot retreat due to barrier")
                        self.clean_abort()
                        return
                    fb = -1

                if gap > self.distance_tolerance:
                    self.movement_attempts += 1
                    if distance_traveled < abs(goal_dx):
                        logging.info(f"Phase 2 - Keep moving. Remaining: {gap}m ")
                        self._move_robot(fb * speed, 0.0, 0.0)
                    elif distance_traveled > abs(goal_dx):
                        logging.debug(
                            f"Phase 2 - OVERSHOOT: move other way. Remaining: {gap}m"
                        )
                        self._move_robot(-1 * fb * 0.2, 0.0, 0.0)
                else:
                    logging.info(
                        "Phase 2 - Movement completed normally, processing next AI command"
                    )
                    self.clean_abort()

        time.sleep(0.1)

    def _process_turn_left(self):
        """
        Process turn left command with safety check.
        """
        if not self.path_provider.turn_left:
            logging.warning("Cannot turn left due to barrier")
            return

        path = random.choice(self.path_provider.turn_left)
        path_angle = self.path_provider.path_angles[path]

        target_yaw = self._normalize_angle(
            -1 * self.odom.position["odom_yaw_m180_p180"] + path_angle
        )
        self.pending_movements.put(
            MoveCommand(
                dx=0.5,
                yaw=round(target_yaw, 2),
                start_x=round(self.odom.position["odom_x"], 2),
                start_y=round(self.odom.position["odom_y"], 2),
                turn_complete=False,
            )
        )

    def _process_turn_right(self):
        """
        Process turn right command with safety check.
        """
        if not self.path_provider.turn_right:
            logging.warning("Cannot turn right due to barrier")
            return

        path = random.choice(self.path_provider.turn_right)
        path_angle = self.path_provider.path_angles[path]

        target_yaw = self._normalize_angle(
            -1 * self.odom.position["odom_yaw_m180_p180"] + path_angle
        )
        self.pending_movements.put(
            MoveCommand(
                dx=0.5,
                yaw=round(target_yaw, 2),
                start_x=round(self.odom.position["odom_x"], 2),
                start_y=round(self.odom.position["odom_y"], 2),
                turn_complete=False,
            )
        )

    def _process_move_forward(self):
        """
        Process move forward command with safety check.
        """
        if not self.path_provider.advance:
            logging.warning("Cannot advance due to barrier")
            return

        path = random.choice(self.path_provider.advance)
        path_angle = self.path_provider.path_angles[path]

        target_yaw = self._normalize_angle(
            -1 * self.odom.position["odom_yaw_m180_p180"] + path_angle
        )
        self.pending_movements.put(
            MoveCommand(
                dx=0.5,
                yaw=target_yaw,
                start_x=round(self.odom.position["odom_x"], 2),
                start_y=round(self.odom.position["odom_y"], 2),
                turn_complete=True if path_angle == 0 else False,
            )
        )

    def _process_move_back(self):
        """
        Process move back command with safety check.
        """
        if not self.path_provider.retreat:
            logging.warning("Cannot retreat due to barrier")
            return

        self.pending_movements.put(
            MoveCommand(
                dx=-0.5,
                yaw=0.0,
                start_x=round(self.odom.position["odom_x"], 2),
                start_y=round(self.odom.position["odom_y"], 2),
                turn_complete=True,
                speed=0.2,
            )
        )

    def _normalize_angle(self, angle: float) -> float:
        """
        Normalize angle to [-180, 180] range.

        Parameters:
        -----------
        angle : float
            Angle in degrees to normalize.

        Returns:
        --------
        float
            Normalized angle in degrees within the range [-180, 180].
        """
        if angle < -180:
            angle += 360.0
        elif angle > 180:
            angle -= 360.0
        return angle

    def _calculate_angle_gap(self, current: float, target: float) -> float:
        """
        Calculate shortest angular distance between two angles.

        Parameters:
        -----------
        current : float
            Current angle in degrees.
        target : float
            Target angle in degrees.

        Returns:
        --------
        float
            Shortest angular distance in degrees, rounded to 2 decimal places.
        """
        gap = current - target
        if gap > 180.0:
            gap -= 360.0
        elif gap < -180.0:
            gap += 360.0
        return round(gap, 2)

    def _execute_turn(self, gap: float) -> bool:
        """
        Execute turn based on gap direction and lidar constraints.

        Parameters:
        -----------
        gap : float
            The angle gap in degrees to turn.

        Returns:
        --------
        bool
            True if the turn was executed successfully, False if blocked by a barrier.
        """
        if gap > 0:  # Turn left
            if not self.path_provider.turn_left:
                logging.warning("Cannot turn left due to barrier")
                return False
            sharpness = min(self.path_provider.turn_left)
            self._move_robot(sharpness * 0.15, 0, self.turn_speed)
        else:  # Turn right
            if not self.path_provider.turn_right:
                logging.warning("Cannot turn right due to barrier")
                return False
            sharpness = 8 - max(self.path_provider.turn_right)
            self._move_robot(sharpness * 0.15, 0, -self.turn_speed)
        return True

    def _zenoh_ai_status_request(self, data: zenoh.Sample):
        """
        Process an incoming AI control status message.

        Parameters
        ----------
        data : zenoh.Sample
            The Zenoh sample received, which should have a 'payload' attribute.
        """
        ai_control_status = AIStatusRequest.deserialize(data.payload.to_bytes())
        logging.info(f"Received AI Control Status message: {ai_control_status}")

        code = ai_control_status.code
        request_id = ai_control_status.request_id

        # Read the current status
        if code == 2:
            ai_status_response = AIStatusResponse(
                header=prepare_header(ai_control_status.header.frame_id),
                request_id=request_id,
                code=1 if self.ai_control_enabled else 0,
                status=String(
                    data=(
                        "AI Control Enabled"
                        if self.ai_control_enabled
                        else "AI Control Disabled"
                    )
                ),
            )
            return self._zenoh_ai_status_response_pub.put(
                ai_status_response.serialize()
            )

        # Enable the AI control
        if code == 1:
            self.ai_control_enabled = True
            logging.info("AI Control Enabled")

            ai_status_response = AIStatusResponse(
                header=prepare_header(ai_control_status.header.frame_id),
                request_id=request_id,
                code=1,
                status=String(data="AI Control Enabled"),
            )
            return self._zenoh_ai_status_response_pub.put(
                ai_status_response.serialize()
            )

        # Disable the AI control
        if code == 0:
            self.ai_control_enabled = False
            logging.info("AI Control Disabled")
            ai_status_response = AIStatusResponse(
                header=prepare_header(ai_control_status.header.frame_id),
                request_id=request_id,
                code=0,
                status=String(data="AI Control Disabled"),
            )

            return self._zenoh_ai_status_response_pub.put(
                ai_status_response.serialize()
            )
