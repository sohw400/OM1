import json
import tempfile
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from runtime.multi_mode.config import (
    ModeConfig,
    ModeSystemConfig,
    TransitionRule,
    TransitionType,
)
from runtime.multi_mode.manager import ModeManager, ModeState


@pytest.fixture
def sample_mode_configs():
    """Sample mode configurations for testing."""
    return {
        "default": ModeConfig(
            name="default",
            display_name="Default Mode",
            description="Default operational mode",
            system_prompt_base="You are a test agent",
            timeout_seconds=300.0,
        ),
        "advanced": ModeConfig(
            name="advanced",
            display_name="Advanced Mode",
            description="Advanced test mode",
            system_prompt_base="You are an advanced test agent",
        ),
        "emergency": ModeConfig(
            name="emergency",
            display_name="Emergency Mode",
            description="Emergency test mode",
            system_prompt_base="EMERGENCY PROTOCOL ACTIVATED",
        ),
    }


@pytest.fixture
def sample_transition_rules():
    """Sample transition rules for testing."""
    return [
        TransitionRule(
            from_mode="default",
            to_mode="advanced",
            transition_type=TransitionType.INPUT_TRIGGERED,
            trigger_keywords=["advanced", "expert", "complex"],
            priority=3,
            cooldown_seconds=5.0,
        ),
        TransitionRule(
            from_mode="*",
            to_mode="emergency",
            transition_type=TransitionType.INPUT_TRIGGERED,
            trigger_keywords=["emergency", "help", "urgent"],
            priority=10,
            cooldown_seconds=0.0,
        ),
        TransitionRule(
            from_mode="advanced",
            to_mode="default",
            transition_type=TransitionType.TIME_BASED,
            timeout_seconds=600.0,
            priority=1,
        ),
        TransitionRule(
            from_mode="emergency",
            to_mode="default",
            transition_type=TransitionType.INPUT_TRIGGERED,
            trigger_keywords=["normal", "safe", "ok"],
            priority=5,
        ),
    ]


@pytest.fixture
def sample_system_config(sample_mode_configs, sample_transition_rules):
    """Sample system configuration for testing."""
    config = ModeSystemConfig(
        name="test_system",
        default_mode="default",
        config_name="test_config",
        allow_manual_switching=True,
        mode_memory_enabled=True,
        api_key="test_api_key",
        robot_ip="192.168.1.100",
    )
    config.modes = sample_mode_configs
    config.transition_rules = sample_transition_rules
    return config


@pytest.fixture
def mode_manager(sample_system_config):
    """Mode manager instance for testing."""
    with (
        patch("runtime.multi_mode.manager.open_zenoh_session"),
        patch("runtime.multi_mode.manager.ModeManager._load_mode_state"),
    ):
        return ModeManager(sample_system_config)


class TestModeState:
    """Test cases for ModeState class."""

    def test_mode_state_creation(self):
        """Test basic mode state creation."""
        state = ModeState(current_mode="test_mode")
        assert state.current_mode == "test_mode"
        assert state.previous_mode is None
        assert isinstance(state.mode_start_time, float)
        assert len(state.transition_history) == 0
        assert state.last_transition_time == 0.0
        assert len(state.user_context) == 0

    def test_mode_state_with_values(self):
        """Test mode state with custom values."""
        history = ["mode1->mode2:manual"]
        context = {"location": "office"}
        state = ModeState(
            current_mode="active",
            previous_mode="inactive",
            transition_history=history,
            user_context=context,
        )
        assert state.current_mode == "active"
        assert state.previous_mode == "inactive"
        assert state.transition_history == history
        assert state.user_context == context


class TestModeManager:
    """Test cases for ModeManager class."""

    def test_initialization(self, mode_manager, sample_system_config):
        """Test mode manager initialization."""
        assert mode_manager.config == sample_system_config
        assert mode_manager.state.current_mode == "default"
        assert len(mode_manager.transition_cooldowns) == 0
        assert len(mode_manager.pending_transitions) == 0
        assert len(mode_manager._transition_callbacks) == 0

    def test_initialization_invalid_default_mode(self, sample_system_config):
        """Test initialization with invalid default mode raises error."""
        sample_system_config.default_mode = "nonexistent"

        with patch("runtime.multi_mode.manager.open_zenoh_session"):
            with pytest.raises(
                ValueError, match="Default mode 'nonexistent' not found"
            ):
                ModeManager(sample_system_config)

    def test_current_mode_config_property(self, mode_manager):
        """Test current_mode_config property."""
        config = mode_manager.current_mode_config
        assert config.name == "default"
        assert config.display_name == "Default Mode"

    def test_current_mode_name_property(self, mode_manager):
        """Test current_mode_name property."""
        assert mode_manager.current_mode_name == "default"

    def test_add_remove_transition_callback(self, mode_manager):
        """Test adding and removing transition callbacks."""
        callback1 = Mock()
        callback2 = Mock()

        mode_manager.add_transition_callback(callback1)
        mode_manager.add_transition_callback(callback2)
        assert len(mode_manager._transition_callbacks) == 2

        mode_manager.remove_transition_callback(callback1)
        assert len(mode_manager._transition_callbacks) == 1
        assert callback2 in mode_manager._transition_callbacks

    @pytest.mark.asyncio
    async def test_notify_transition_callbacks_sync(self, mode_manager):
        """Test notifying synchronous transition callbacks."""
        callback = Mock()
        mode_manager.add_transition_callback(callback)

        await mode_manager._notify_transition_callbacks("from", "to")
        callback.assert_called_once_with("from", "to")

    @pytest.mark.asyncio
    async def test_notify_transition_callbacks_async(self, mode_manager):
        """Test notifying asynchronous transition callbacks."""
        callback = AsyncMock()
        mode_manager.add_transition_callback(callback)

        await mode_manager._notify_transition_callbacks("from", "to")
        callback.assert_called_once_with("from", "to")

    @pytest.mark.asyncio
    async def test_notify_transition_callbacks_exception(self, mode_manager):
        """Test that callback exceptions are handled gracefully."""

        def error_callback(from_mode, to_mode):
            raise Exception("Callback error")

        mode_manager.add_transition_callback(error_callback)

        await mode_manager._notify_transition_callbacks("from", "to")

    async def test_check_time_based_transitions_no_timeout(self, mode_manager):
        """Test time-based transitions when current mode has no timeout."""
        result = await mode_manager.check_time_based_transitions()
        assert result is None

    async def test_check_time_based_transitions_within_timeout(self, mode_manager):
        """Test time-based transitions within timeout period."""
        mode_manager.config.modes["default"].timeout_seconds = 3600.0
        result = await mode_manager.check_time_based_transitions()
        assert result is None

    async def test_check_time_based_transitions_exceeded_timeout(self, mode_manager):
        """Test time-based transitions when timeout is exceeded."""
        mode_manager.state.current_mode = "advanced"
        mode_manager.config.modes["advanced"].timeout_seconds = 0.1
        mode_manager.state.mode_start_time = time.time() - 1.0

        result = await mode_manager.check_time_based_transitions()
        assert result == "default"

    def test_check_input_triggered_transitions_no_input(self, mode_manager):
        """Test input-triggered transitions with no input."""
        result = mode_manager.check_input_triggered_transitions(None)
        assert result is None

        result = mode_manager.check_input_triggered_transitions("")
        assert result is None

    def test_check_input_triggered_transitions_matching_keyword(self, mode_manager):
        """Test input-triggered transitions with matching keyword."""
        result = mode_manager.check_input_triggered_transitions("I need advanced mode")
        assert result == "advanced"

    def test_check_input_triggered_transitions_emergency_priority(self, mode_manager):
        """Test that emergency mode takes priority due to higher priority value."""
        result = mode_manager.check_input_triggered_transitions(
            "advanced emergency help"
        )
        assert result == "emergency"

    def test_check_input_triggered_transitions_no_match(self, mode_manager):
        """Test input-triggered transitions with no matching keywords."""
        result = mode_manager.check_input_triggered_transitions("just some random text")
        assert result is None

    def test_check_input_triggered_transitions_wildcard_from_mode(self, mode_manager):
        """Test input-triggered transitions with wildcard from_mode."""
        mode_manager.state.current_mode = "advanced"

        result = mode_manager.check_input_triggered_transitions("emergency help needed")
        assert result == "emergency"

    def test_can_transition_success(self, mode_manager, sample_transition_rules):
        """Test successful transition validation."""
        rule = sample_transition_rules[0]
        result = mode_manager._can_transition(rule)
        assert result is True

    def test_can_transition_cooldown_active(
        self, mode_manager, sample_transition_rules
    ):
        """Test transition blocked by active cooldown."""
        rule = sample_transition_rules[0]
        transition_key = "default->advanced"
        mode_manager.transition_cooldowns[transition_key] = time.time()

        result = mode_manager._can_transition(rule)
        assert result is False

    def test_can_transition_cooldown_expired(
        self, mode_manager, sample_transition_rules
    ):
        """Test transition allowed after cooldown expires."""
        rule = sample_transition_rules[0]
        transition_key = "default->advanced"
        mode_manager.transition_cooldowns[transition_key] = time.time() - 10.0

        result = mode_manager._can_transition(rule)
        assert result is True

    def test_can_transition_invalid_target_mode(self, mode_manager):
        """Test transition blocked by invalid target mode."""
        rule = TransitionRule(
            from_mode="default",
            to_mode="nonexistent",
            transition_type=TransitionType.MANUAL,
        )

        result = mode_manager._can_transition(rule)
        assert result is False

    @pytest.mark.asyncio
    async def test_request_transition_manual_disabled(self, mode_manager):
        """Test manual transition request when manual switching is disabled."""
        mode_manager.config.allow_manual_switching = False

        result = await mode_manager.request_transition("advanced", "manual")
        assert result is False

    @pytest.mark.asyncio
    async def test_request_transition_invalid_target(self, mode_manager):
        """Test manual transition request to invalid target mode."""
        result = await mode_manager.request_transition("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_request_transition_same_mode(self, mode_manager):
        """Test manual transition request to same mode."""
        result = await mode_manager.request_transition("default")
        assert result is True

    @pytest.mark.asyncio
    async def test_request_transition_success(self, mode_manager):
        """Test successful manual transition request."""
        with patch.object(
            mode_manager, "_execute_transition", return_value=True
        ) as mock_execute:
            result = await mode_manager.request_transition("advanced")
            assert result is True
            mock_execute.assert_called_once_with("advanced", "manual")

    @pytest.mark.asyncio
    async def test_execute_transition_success(self, mode_manager):
        """Test successful transition execution."""
        callback = AsyncMock()
        mode_manager.add_transition_callback(callback)

        with patch.object(mode_manager, "_save_mode_state") as mock_save:
            result = await mode_manager._execute_transition("advanced", "test_reason")

            assert result is True
            assert mode_manager.state.current_mode == "advanced"
            assert mode_manager.state.previous_mode == "default"
            assert len(mode_manager.state.transition_history) == 1
            assert (
                "default->advanced:test_reason" in mode_manager.state.transition_history
            )

            callback.assert_called_once_with("default", "advanced")
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_transition_history_limit(self, mode_manager):
        """Test that transition history is limited to prevent excessive growth."""
        mode_manager.state.transition_history = [f"transition_{i}" for i in range(60)]

        with patch.object(mode_manager, "_save_mode_state"):
            await mode_manager._execute_transition("advanced", "test")

            assert len(mode_manager.state.transition_history) == 25

    @pytest.mark.asyncio
    async def test_execute_transition_exception(self, mode_manager):
        """Test transition execution with exception in callback."""

        def error_callback(from_mode, to_mode):
            raise Exception("Callback error")

        mode_manager.add_transition_callback(error_callback)

        result = await mode_manager._execute_transition("advanced", "test")
        assert result is True

    def test_get_available_transitions(self, mode_manager):
        """Test getting available transitions from current mode."""
        transitions = mode_manager.get_available_transitions()
        assert isinstance(transitions, list)
        assert "advanced" in transitions
        assert "emergency" in transitions

    def test_get_available_transitions_from_advanced(self, mode_manager):
        """Test getting available transitions from advanced mode."""
        mode_manager.state.current_mode = "advanced"
        transitions = mode_manager.get_available_transitions()

        assert "emergency" in transitions
        assert "default" in transitions

    def test_get_mode_info(self, mode_manager):
        """Test getting current mode information."""
        info = mode_manager.get_mode_info()

        assert info["current_mode"] == "default"
        assert info["display_name"] == "Default Mode"
        assert info["description"] == "Default operational mode"
        assert isinstance(info["mode_duration"], float)
        assert info["previous_mode"] is None
        assert isinstance(info["available_transitions"], list)
        assert isinstance(info["all_modes"], list)
        assert len(info["all_modes"]) == 3
        assert isinstance(info["transition_history"], list)
        assert info["timeout_seconds"] == 300.0
        assert isinstance(info["time_remaining"], float)

    def test_get_mode_info_no_timeout(self, mode_manager):
        """Test getting mode info when current mode has no timeout."""
        mode_manager.state.current_mode = "advanced"
        info = mode_manager.get_mode_info()

        assert info["timeout_seconds"] is None
        assert info["time_remaining"] is None

    def test_update_user_context(self, mode_manager):
        """Test updating user context."""
        context = {"location": "office", "activity": "meeting"}
        mode_manager.update_user_context(context)

        assert mode_manager.state.user_context == context

    def test_update_user_context_merge(self, mode_manager):
        """Test that user context updates merge with existing context."""
        mode_manager.state.user_context = {"existing": "value"}
        mode_manager.update_user_context({"new": "data"})

        expected = {"existing": "value", "new": "data"}
        assert mode_manager.state.user_context == expected

    def test_get_user_context(self, mode_manager):
        """Test getting user context."""
        original_context = {"test": "data"}
        mode_manager.state.user_context = original_context

        context = mode_manager.get_user_context()
        assert context == original_context
        assert context is not original_context

    @pytest.mark.asyncio
    async def test_process_tick_time_transition(self, mode_manager):
        """Test process_tick with time-based transition."""
        with patch.object(
            mode_manager, "check_time_based_transitions", return_value="advanced"
        ):
            with patch.object(
                mode_manager, "_execute_transition", return_value=True
            ) as mock_execute:
                result = await mode_manager.process_tick()

                assert result == "advanced"
                mock_execute.assert_called_once_with("advanced", "timeout")

    @pytest.mark.asyncio
    async def test_process_tick_input_transition(self, mode_manager):
        """Test process_tick with input-triggered transition."""
        with patch.object(
            mode_manager, "check_time_based_transitions", return_value=None
        ):
            with patch.object(
                mode_manager,
                "check_input_triggered_transitions",
                return_value="emergency",
            ):
                with patch.object(
                    mode_manager, "_execute_transition", return_value=True
                ) as mock_execute:
                    result = await mode_manager.process_tick("emergency help")

                    assert result == "emergency"
                    mock_execute.assert_called_once_with("emergency", "input_triggered")

    @pytest.mark.asyncio
    async def test_process_tick_no_transition(self, mode_manager):
        """Test process_tick with no transitions triggered."""
        with patch.object(
            mode_manager, "check_time_based_transitions", return_value=None
        ):
            with patch.object(
                mode_manager, "check_input_triggered_transitions", return_value=None
            ):
                result = await mode_manager.process_tick("normal input")

                assert result is None

    @pytest.mark.asyncio
    async def test_process_tick_failed_transition(self, mode_manager):
        """Test process_tick with failed transition execution."""
        with patch.object(
            mode_manager, "check_time_based_transitions", return_value="advanced"
        ):
            with patch.object(mode_manager, "_execute_transition", return_value=False):
                result = await mode_manager.process_tick()

                assert result is None

    def test_get_state_file_path(self, mode_manager):
        """Test getting state file path."""
        path = mode_manager._get_state_file_path()
        assert path.endswith(".test_config.json5")
        assert "memory" in path

    def test_save_mode_state_disabled(self, mode_manager):
        """Test that state saving is skipped when memory is disabled."""
        mode_manager.config.mode_memory_enabled = False

        mode_manager._save_mode_state()

    def test_save_mode_state_success(self, mode_manager):
        """Test successful state saving."""
        mode_manager.state.current_mode = "advanced"
        mode_manager.state.previous_mode = "default"
        mode_manager.state.transition_history = ["default->advanced:test"]

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(mode_manager, "_get_state_file_path") as mock_path:
                state_file = f"{temp_dir}/test_state.json5"
                mock_path.return_value = state_file

                mode_manager._save_mode_state()

                with open(state_file, "r") as f:
                    saved_data = json.load(f)

                assert saved_data["last_active_mode"] == "advanced"
                assert saved_data["previous_mode"] == "default"
                assert saved_data["transition_history"] == ["default->advanced:test"]
                assert "timestamp" in saved_data

    def test_load_mode_state_no_file(self, mode_manager, sample_system_config):
        """Test loading state when no state file exists."""
        with patch.object(
            mode_manager, "_get_state_file_path", return_value="/nonexistent/file.json5"
        ):
            mode_manager._load_mode_state()

            assert mode_manager.state.current_mode == sample_system_config.default_mode

    def test_load_mode_state_success(self, mode_manager):
        """Test successful state loading."""
        saved_state = {
            "last_active_mode": "advanced",
            "previous_mode": "default",
            "timestamp": time.time(),
            "transition_history": ["default->advanced:test"],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json5", delete=False) as f:
            json.dump(saved_state, f)
            temp_file = f.name

        try:
            with patch.object(
                mode_manager, "_get_state_file_path", return_value=temp_file
            ):
                mode_manager._load_mode_state()

                assert mode_manager.state.current_mode == "advanced"
                assert mode_manager.state.previous_mode == "default"
                assert mode_manager.state.transition_history == [
                    "default->advanced:test"
                ]
        finally:
            import os

            os.unlink(temp_file)

    def test_load_mode_state_invalid_mode(self, mode_manager):
        """Test loading state with invalid mode falls back to default."""
        saved_state = {
            "last_active_mode": "nonexistent_mode",
            "previous_mode": "default",
            "timestamp": time.time(),
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json5", delete=False) as f:
            json.dump(saved_state, f)
            temp_file = f.name

        try:
            with patch.object(
                mode_manager, "_get_state_file_path", return_value=temp_file
            ):
                mode_manager._load_mode_state()

                assert mode_manager.state.current_mode == "default"
        finally:
            import os

            os.unlink(temp_file)

    def test_load_mode_state_corrupted_file(self, mode_manager):
        """Test loading state with corrupted file falls back to default."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json5", delete=False) as f:
            f.write("invalid json content")
            temp_file = f.name

        try:
            with patch.object(
                mode_manager, "_get_state_file_path", return_value=temp_file
            ):
                mode_manager._load_mode_state()

                assert mode_manager.state.current_mode == "default"
        finally:
            import os

            os.unlink(temp_file)
