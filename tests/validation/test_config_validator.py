import pytest

from validation import (
    ConfigValidationError,
    validate_choice,
    validate_range,
    validate_required,
    validate_type,
)


class TestValidateRequired:
    def test_required_field_present(self):
        config = {"api_key": "test_key"}
        value = validate_required(config, "api_key")
        assert value == "test_key"

    def test_required_field_missing(self):
        config = {}
        with pytest.raises(ConfigValidationError, match="Required field 'api_key' is missing"):
            validate_required(config, "api_key")

    def test_required_field_none(self):
        config = {"api_key": None}
        with pytest.raises(ConfigValidationError, match="Required field 'api_key' is missing"):
            validate_required(config, "api_key")

    def test_required_field_empty_string(self):
        config = {"api_key": ""}
        with pytest.raises(ConfigValidationError, match="Required field 'api_key' is missing"):
            validate_required(config, "api_key")

    def test_required_with_config_name(self):
        config = {}
        with pytest.raises(
            ConfigValidationError, match="Required field 'api_key' is missing in test_config"
        ):
            validate_required(config, "api_key", "test_config")

    def test_required_from_object(self):
        class Config:
            def __init__(self):
                self.api_key = "test_key"

        config = Config()
        value = validate_required(config, "api_key")
        assert value == "test_key"


class TestValidateType:
    def test_valid_type_single(self):
        validate_type("test", str, "field_name")

    def test_invalid_type_single(self):
        with pytest.raises(ConfigValidationError, match="Field 'field_name' must be str"):
            validate_type(123, str, "field_name")

    def test_valid_type_multiple(self):
        validate_type(10, (int, float), "hertz")
        validate_type(10.5, (int, float), "hertz")

    def test_invalid_type_multiple(self):
        with pytest.raises(ConfigValidationError, match="Field 'hertz' must be int or float"):
            validate_type("invalid", (int, float), "hertz")

    def test_type_with_config_name(self):
        with pytest.raises(
            ConfigValidationError,
            match="Field 'hertz' in test_config must be int, got str",
        ):
            validate_type("invalid", int, "hertz", "test_config")


class TestValidateRange:
    def test_valid_range_both_bounds(self):
        validate_range(5, "port", min_value=1, max_value=65535)

    def test_valid_range_min_only(self):
        validate_range(100, "value", min_value=0)

    def test_valid_range_max_only(self):
        validate_range(50, "percentage", max_value=100)

    def test_below_min_value(self):
        with pytest.raises(
            ConfigValidationError, match="Field 'hertz' must be >= 0.001, got -1"
        ):
            validate_range(-1, "hertz", min_value=0.001)

    def test_above_max_value(self):
        with pytest.raises(
            ConfigValidationError, match="Field 'percentage' must be <= 100, got 150"
        ):
            validate_range(150, "percentage", max_value=100)

    def test_range_with_config_name(self):
        with pytest.raises(
            ConfigValidationError,
            match="Field 'hertz' in spot.json5 must be >= 0.001, got 0",
        ):
            validate_range(0, "hertz", min_value=0.001, config_name="spot.json5")


class TestValidateChoice:
    def test_valid_choice(self):
        validate_choice("option1", ["option1", "option2", "option3"], "mode")

    def test_invalid_choice(self):
        with pytest.raises(
            ConfigValidationError,
            match="Field 'mode' must be one of \\['option1', 'option2'\\], got 'invalid'",
        ):
            validate_choice("invalid", ["option1", "option2"], "mode")

    def test_choice_with_numbers(self):
        validate_choice(5, [1, 5, 10], "level")

    def test_choice_with_config_name(self):
        with pytest.raises(
            ConfigValidationError,
            match="Field 'mode' in test_config must be one of",
        ):
            validate_choice("invalid", ["A", "B"], "mode", "test_config")


class TestIntegration:
    def test_complete_config_validation(self):
        config = {
            "hertz": 10,
            "name": "test_agent",
            "port": 8080,
            "mode": "development",
        }

        hertz = validate_required(config, "hertz")
        validate_type(hertz, (int, float), "hertz")
        validate_range(hertz, "hertz", min_value=0.001)

        name = validate_required(config, "name")
        validate_type(name, str, "name")

        port = validate_required(config, "port")
        validate_type(port, int, "port")
        validate_range(port, "port", min_value=1, max_value=65535)

        mode = validate_required(config, "mode")
        validate_choice(mode, ["development", "production"], "mode")

    def test_validation_with_invalid_config(self):
        config = {"hertz": -5, "name": 123}

        hertz = validate_required(config, "hertz")
        validate_type(hertz, (int, float), "hertz")

        with pytest.raises(ConfigValidationError):
            validate_range(hertz, "hertz", min_value=0.001)
