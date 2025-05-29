import logging
import math
import random
import threading
import time
from enum import Enum
from queue import Queue

from actions.base import ActionConfig, ActionConnector
from actions.move_go2_autonomy.interface import MoveInput
from providers.odom_provider import OdomProvider
from providers.rplidar_provider import RPLidarProvider
from unitree.unitree_sdk2py.go2.sport.sport_client import SportClient


class RobotState(Enum):
    STANDING = "standing"
    SITTING = "sitting"


class MoveUnitreeSDKConnector(ActionConnector[MoveInput]):

    def __init__(self, config: ActionConfig):
        super().__init__(config)

        self.dog_attitude = None
        self.dog_moving = None

        self.move_speed = 0.7
        self.turn_speed = 0.6

        self.angle_tolerance = 5.0
        self.distance_tolerance = 0.05  # m
        self.pending_movements = Queue()
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.yaw_now = 0.0
        self.movement_attempts = 0

        self.lidar_on = False
        self.lidar = None

        self.turn_left = []
        self.advance = []
        self.turn_right = []
        self.retreat = []

        self.lidar = RPLidarProvider()
        self.lidar_on = self.lidar.running

        self.motion_buffer = None

        # create sport client
        self.sport_client = None
        try:
            self.sport_client = SportClient()
            self.sport_client.SetTimeout(10.0)
            self.sport_client.Init()
            # self.sport_client.Move(0.1, 0, 0)
            logging.info("Autonomy Unitree sport client initialized")
        except Exception as e:
            logging.error(f"Error initializing Unitree sport client: {e}")

        self.odom = OdomProvider()
        logging.info(f"Autonomy Odom Provider: {self.odom}")

        self.thread_lock = threading.Lock()

    def _execute_command_thread(self, command: str) -> None:

        try:
            if command == "StandUp" and self.dog_attitude == RobotState.STANDING:
                logging.info("Already standing, skipping command")
                return
            elif command == "StandDown" and self.dog_attitude == RobotState.SITTING:
                logging.info("Already sitting, skipping command")
                return

            code = getattr(self.sport_client, command)()
            logging.info(f"Unitree command {command} executed with code {code}")

        except Exception as e:
            logging.error(f"Error in command thread {command}: {e}")
        finally:
            self.thread_lock.release()

    def _execute_sport_command_sync(self, command: str) -> None:

        if not self.sport_client:
            return

        if not self.thread_lock.acquire(blocking=False):
            logging.info("Action already in progress, skipping")
            return

        try:
            thread = threading.Thread(
                target=self._execute_command_thread, args=(command,), daemon=True
            )
            thread.start()
        except Exception as e:
            logging.error(f"Error executing Unitree command {command}: {e}")
            self.thread_lock.release()

    async def _execute_sport_command(self, command: str) -> None:

        if not self.sport_client:
            return

        if not self.thread_lock.acquire(blocking=False):
            logging.info("Action already in progress, skipping")
            return

        try:
            thread = threading.Thread(
                target=self._execute_command_thread, args=(command,), daemon=True
            )
            thread.start()
        except Exception as e:
            logging.error(f"Error executing Unitree command {command}: {e}")
            self.thread_lock.release()

    async def connect(self, output_interface: MoveInput) -> None:

        # this is used only by the LLM
        logging.info(f"AI command.connect: {output_interface.action}")

        self.odomDataRefresh()

        if self.dog_moving:
            # for example due to a teleops or game controller command
            logging.info("Disregard new AI movement command - robot is already moving")
            return

        if self.pending_movements.qsize() > 0:
            logging.info("Movement in progress: disregarding new AI command")
            return

        if self.x == 0.0:
            # this value is never precisely zero EXCEPT while
            # booting and waiting for data to arrive
            logging.info("Waiting for location data")
            return

        if output_interface.action == "turn left":
            # turn 90 Deg to the left (CCW)
            if len(self.turn_left) == 0:
                logging.warning("Cannot turn left due to barrier")
                return
            path = random.choice(self.turn_left)
            logging.info(f"Path choice: {path}")
            # ToDo - use specific path value for tight/soft turns
            # hardcode for now
            target_yaw = self.yaw_now - 90.0
            if target_yaw <= -180:
                target_yaw += 360.0
            self.pending_movements.put([0.0, target_yaw, "turn"])
        elif output_interface.action == "turn right":
            # turn 90 Deg to the right (CW)
            if len(self.turn_right) == 0:
                logging.warning("Cannot turn right due to barrier")
                return
            path = random.choice(self.turn_right)
            logging.info(f"Path choice: {path}")
            # ToDo - use specific path value for tight/soft turns
            # hardcode for now
            target_yaw = self.yaw_now + 90.0
            if target_yaw >= 180.0:
                target_yaw -= 360.0
            self.pending_movements.put([0.0, target_yaw, "turn"])
        elif output_interface.action == "move forwards":
            if len(self.advance) == 0:
                logging.warning("Cannot advance due to barrier")
                return
            self.pending_movements.put([0.5, 0.0, "advance", self.x, self.y])
        elif output_interface.action == "move back":
            if len(self.retreat) == 0:
                logging.warning("Cannot retreat due to barrier")
                return
            self.pending_movements.put([0.5, 0.0, "retreat", self.x, self.y])
        elif output_interface.action == "stand still":
            logging.info(f"AI movement command: {output_interface.action}")
            # do nothing
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

    def odomDataRefresh(self):
        if hasattr(self.odom, "running"):
            if self.odom.running:
                nav = self.odom.odom
                logging.debug(f"Go2 Odom data: {nav}")

                if nav["body_attitude"] == "standing":
                    self.dog_attitude = RobotState.STANDING
                else:
                    self.dog_attitude = RobotState.SITTING

                if nav["moving"]:
                    # for conceptual clarity
                    self.dog_moving = True
                else:
                    self.dog_moving = False

                self.yaw_now = nav["yaw_odom_m180_p180"]
                # CW yaw = positive

                # current position in world frame
                self.x = nav["x"]
                self.y = nav["y"]

                logging.debug(
                    f"Go2 x,y,yaw: {round(self.x,2)},{round(self.y,2)},{round(self.yaw_now,2)}"
                )

                if self.lidar:
                    # reconfirm possible paths using centralized logic
                    # this is needed due to the 2s latency of the LLMs
                    possible_paths = self.lidar.valid_paths
                    logging.info(f"Action - Valid paths: {possible_paths}")
                    if possible_paths is not None:
                        self.turn_left, self.advance, self.turn_right, self.retreat, _ = \
                            RPLidarProvider.categorize_paths_static(possible_paths)

            else:
                logging.warn("Go2 x,y,yaw: NAVIGATION NOT PROVIDING DATA")

    def _move_robot(self, vx, vy, vturn=0.0) -> None:

        logging.info(f"_move_robot: vx={vx}, vy={vy}, vturn={vturn}")

        if not self.sport_client:
            return

        if self.dog_attitude != RobotState.STANDING:
            return

        try:
            logging.info(f"self.sport_client.Move: vx={vx}, vy={vy}, vturn={vturn}")
            # do not actually move during testing
            self.sport_client.Move(vx, vy, vturn)
        except Exception as e:
            logging.error(f"Error moving robot: {e}")

    def tick(self) -> None:

        logging.info("AI Motion Tick")

        self.odomDataRefresh()

        if self.x == 0.0:
            # this value is never precisely zero except while
            # booting and waiting for data to arrive
            logging.info("Waiting for odom data")
            time.sleep(0.1)
            return

        if self.dog_attitude != RobotState.STANDING:
            logging.info("Cannot move - dog is sitting")
            time.sleep(0.1)
            return

        # if we got to this point, we have good data and we are able to
        # safely proceed
        target = list(self.pending_movements.queue)

        if len(target) > 0:

            current_target = target[0]

            logging.info(f"Target: {current_target} current yaw: {self.yaw_now}")

            if self.movement_attempts > 10:
                # abort - we are not converging
                self.movement_attempts = 0
                self.pending_movements.get()
                logging.info("TIMEOUT - AI movement command timeout - not converging")
                return

            goal_dx = current_target[0]
            goal_yaw = current_target[1]
            direction = current_target[2]

            if "turn" in direction:
                gap = self.yaw_now - goal_yaw
                if gap > 180.0:
                    gap -= 360.0
                elif gap < -180.0:
                    gap += 360.0
                logging.info(f"remaining turn GAP: {round(gap,2)}")
                if abs(gap) > 10.0:
                    logging.debug("gap is big, using large displacements")
                    if gap > 0:
                        self.movement_attempts += 1
                        if len(self.turn_left) < 4:
                            logging.warning("Cannot turn left due to barrier")
                            return
                        # turn combines forward motion with rotation
                        self._move_robot(0.5, 0, 0.5)
                    elif gap < 0:
                        self.movement_attempts += 1
                        if len(self.turn_right) < 4:
                            logging.warning("Cannot turn right due to barrier")
                            return
                        # turn combines forward motion with rotation
                        self._move_robot(0.5, 0, -0.5)
                elif abs(gap) > self.angle_tolerance and abs(gap) <= 10.0:
                    logging.debug("gap is getting smaller, using smaller steps")
                    if gap > 0:
                        self.movement_attempts += 1
                        if len(self.turn_left) < 4:
                            logging.warning("Cannot turn left due to barrier")
                            return
                        self._move_robot(0.2, 0, 0.2)
                    elif gap < 0:
                        self.movement_attempts += 1
                        if len(self.turn_right) < 4:
                            logging.warning("Cannot turn right due to barrier")
                            return
                        self._move_robot(0.2, 0, -0.2)
                elif abs(gap) <= self.angle_tolerance:
                    logging.info(
                        "turn is completed, gap is small enough, done, pop 1 off queue"
                    )
                    self.movement_attempts = 0
                    self.pending_movements.get()
            else:
                # reconfirm possible paths
                pp = self.lidar.valid_paths

                logging.debug(f"Action move/advance - Valid paths: {pp}")

                s_x = target[0][3]
                s_y = target[0][4]
                distance_traveled = math.sqrt((self.x - s_x) ** 2 + (self.y - s_y) ** 2)
                remaining = abs(goal_dx - distance_traveled)
                logging.info(f"remaining advance GAP: {round(remaining,2)}")

                fb = 0
                if "advance" in direction and len(self.advance) == 1:
                    fb = 1
                elif "retreat" in direction and len(self.retreat) == 1:
                    fb = -1
                else:
                    logging.info("danger, pop 1 off queue")
                    self.movement_attempts = 0
                    self.pending_movements.get()
                    return

                if remaining > self.distance_tolerance:
                    if distance_traveled < goal_dx:  # keep advancing
                        logging.info(f"keep moving. remaining:{remaining} ")
                        self.movement_attempts += 1
                        self._move_robot(fb * 0.5, 0.0, 0.0)
                    elif distance_traveled > goal_dx:  # you moved too far
                        logging.debug(
                            f"OVERSHOOT: move other way. remaining:{remaining} "
                        )
                        self.movement_attempts += 1
                        self._move_robot(-1 * fb * 0.2, 0.0, 0.0)
                else:
                    logging.info(
                        "advance is completed, gap is small enough, done, pop 1 off queue"
                    )
                    self.movement_attempts = 0
                    self.pending_movements.get()

        time.sleep(0.1)
