from dataclasses import dataclass
from enum import Enum

from actions.base import Interface


class MovementAction(str, Enum):
    # shake_hand = "shake hand"
    # high_five = "high five"
    # hug = "hug"
    face_wave = "face wave"
    high_wave = "high wave"
    clap = "clap"
    left_kiss = "left kiss"
    # heart = "heart"
    # right_heart = "right heart"
    # hands_up = "hands up"
    # x_ray = "x-ray"
    # right_hand_up = "right hand up"
    # reject = "reject"
    right_kiss = "right kiss"
    two_hand_kiss = "two-hand kiss"

@dataclass
class MoveInput:
    action: MovementAction


@dataclass
class Move(Interface[MoveInput, MoveInput]):
    """
    A movement to be performed by the agent.
    Effect: Allows the agent to move.
    """

    input: MoveInput
    output: MoveInput
