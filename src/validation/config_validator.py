"""
Configuration validation utilities.

Provides functions for validating configuration parameters with clear error messages.
"""

from typing import Any, List, Optional, Type, Union


class ConfigValidationError(ValueError):
    """Raised when configuration validation fails."""

    pass


def validate_required(
    config: Any, field_name: str, config_name: Optional[str] = None
) -> Any:
    """
    Check if a required field exists in the configuration.

    Parameters
    ----------
    config : Any
        Configuration object or dictionary
    field_name : str
        Name of the required field
    config_name : Optional[str]
        Name of the configuration for error messages

    Returns
    -------
    Any
        The value of the field

    Raises
    ------
    ConfigValidationError
        If the field is missing or None
    """
    if isinstance(config, dict):
        value = config.get(field_name)
    else:
        value = getattr(config, field_name, None)

    if value is None or (isinstance(value, str) and value == ""):
        context = f" in {config_name}" if config_name else ""
        raise ConfigValidationError(f"Required field '{field_name}' is missing{context}")

    return value


def validate_type(
    value: Any,
    expected_type: Union[Type, tuple],
    field_name: str,
    config_name: Optional[str] = None,
) -> None:
    """
    Validate that a value has the expected type.

    Parameters
    ----------
    value : Any
        Value to validate
    expected_type : Union[Type, tuple]
        Expected type or tuple of types
    field_name : str
        Name of the field being validated
    config_name : Optional[str]
        Name of the configuration for error messages

    Raises
    ------
    ConfigValidationError
        If the value type doesn't match expected type
    """
    if not isinstance(value, expected_type):
        context = f" in {config_name}" if config_name else ""
        if isinstance(expected_type, tuple):
            type_names = " or ".join(t.__name__ for t in expected_type)
        else:
            type_names = expected_type.__name__
        raise ConfigValidationError(
            f"Field '{field_name}'{context} must be {type_names}, "
            f"got {type(value).__name__}"
        )


def validate_range(
    value: Union[int, float],
    field_name: str,
    min_value: Optional[Union[int, float]] = None,
    max_value: Optional[Union[int, float]] = None,
    config_name: Optional[str] = None,
) -> None:
    """
    Validate that a numeric value is within the specified range.

    Parameters
    ----------
    value : Union[int, float]
        Value to validate
    field_name : str
        Name of the field being validated
    min_value : Optional[Union[int, float]]
        Minimum allowed value (inclusive)
    max_value : Optional[Union[int, float]]
        Maximum allowed value (inclusive)
    config_name : Optional[str]
        Name of the configuration for error messages

    Raises
    ------
    ConfigValidationError
        If the value is outside the specified range
    """
    context = f" in {config_name}" if config_name else ""

    if min_value is not None and value < min_value:
        raise ConfigValidationError(
            f"Field '{field_name}'{context} must be >= {min_value}, got {value}"
        )

    if max_value is not None and value > max_value:
        raise ConfigValidationError(
            f"Field '{field_name}'{context} must be <= {max_value}, got {value}"
        )


def validate_choice(
    value: Any,
    valid_choices: List[Any],
    field_name: str,
    config_name: Optional[str] = None,
) -> None:
    """
    Validate that a value is one of the allowed choices.

    Parameters
    ----------
    value : Any
        Value to validate
    valid_choices : List[Any]
        List of valid choices
    field_name : str
        Name of the field being validated
    config_name : Optional[str]
        Name of the configuration for error messages

    Raises
    ------
    ConfigValidationError
        If the value is not in the list of valid choices
    """
    if value not in valid_choices:
        context = f" in {config_name}" if config_name else ""
        choices_str = ", ".join(repr(c) for c in valid_choices)
        raise ConfigValidationError(
            f"Field '{field_name}'{context} must be one of [{choices_str}], "
            f"got {repr(value)}"
        )
