from dataclasses import dataclass
from typing import Optional

from actions.base import Interface


class RememberLocationInput:
    """
    Input payload for remembering a named location.

    This class intentionally accepts multiple possible initialization
    keywords so older code that passes `action=` will still work.

    Fields
    ------
    label: str
        Human-readable name for the location (e.g. "kitchen").
    description: Optional[str]
        Optional textual description of the location.
    """

    # type hints are required so function_schemas.generate_function_schema_from_action
    # can inspect the expected fields (it uses typing.get_type_hints)
    label: str
    description: Optional[str]

    def __init__(
        self,
        label: str = "",
        description: Optional[str] = "",
        action: Optional[str] = None,
        **kwargs,
    ) -> None:
        # Accept legacy 'action' kw (from orchestrator) and prefer it when provided
        if action and not label:
            label = action
        # Also accept 'text'/'message' if present in kwargs
        if not label:
            for alt in ("text", "message", "value", "command"):
                if alt in kwargs and isinstance(kwargs[alt], str):
                    label = kwargs[alt]
                    break

        self.label = label
        self.description = description or ""


@dataclass
class RememberLocation(Interface[RememberLocationInput, RememberLocationInput]):
    """
    Action interface for remembering a location. The LLM will call this
    action with a `label` and the connector will persist it (via API).
    """

    input: RememberLocationInput
    output: RememberLocationInput
