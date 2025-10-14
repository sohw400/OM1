from dataclasses import dataclass
from typing import Optional

from actions.base import Interface


class NavigateLocationInput:
    """
    Input payload for navigating to a remembered location.

    Accepts multiple init signatures for backward compatibility with the
    orchestrator which may pass `action=...`.
    """

    # type hints are used by the function schema generator
    label: str
    description: Optional[str]

    def __init__(
        self,
        label: str = "",
        description: Optional[str] = "",
        action: Optional[str] = None,
        **kwargs,
    ) -> None:
        if action and not label:
            label = action
        if not label:
            for alt in ("text", "message", "value", "command"):
                if alt in kwargs and isinstance(kwargs[alt], str):
                    label = kwargs[alt]
                    break

        self.label = label
        self.description = description or ""


@dataclass
class NavigateLocation(Interface[NavigateLocationInput, NavigateLocationInput]):
    input: NavigateLocationInput
    output: NavigateLocationInput
