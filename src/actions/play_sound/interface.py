from dataclasses import dataclass
from enum import Enum

from actions.base import Interface


class MovementAction(str, Enum):
    SRPING = "spring"
    SUMMER = "summer"
    FALL = "fall"
    WINTER = "winter"


@dataclass
class MoveInput:
    action: MovementAction


@dataclass
class Move(Interface[MoveInput, MoveInput]):
    """
    A sound to be played by the agent.
    Effect: Allows the agent to play a sound.
    """

    input: MoveInput
    output: MoveInput
