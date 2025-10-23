import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import json5

from actions import load_action
from actions.base import AgentAction
from backgrounds import load_background
from backgrounds.base import Background, BackgroundConfig
from inputs import load_input
from inputs.base import Sensor, SensorConfig
from llm import LLM, LLMConfig, load_llm
from runtime.multi_mode.hook import (
    LifecycleHook,
    LifecycleHookType,
    execute_lifecycle_hooks,
    parse_lifecycle_hooks,
)
from runtime.robotics import load_unitree
from runtime.single_mode.config import RuntimeConfig, add_meta
from simulators import load_simulator
from simulators.base import Simulator, SimulatorConfig


class TransitionType(Enum):
    """
    Types of mode transitions.

    - INPUT_TRIGGERED: Switch based on specific input keywords or phrases.
    - TIME_BASED: Switch after a certain time period or at specific times.
    - CONTEXT_AWARE: Switch based on contextual cues or environment
    - MANUAL: Switch only when manually triggered by the user.
    """

    INPUT_TRIGGERED = "input_triggered"
    TIME_BASED = "time_based"
    CONTEXT_AWARE = "context_aware"
    MANUAL = "manual"


@dataclass
class TransitionRule:
    """
    Defines a rule for transitioning between modes.

    Parameters
    ----------
    from_mode : str
        Name of the mode to transition from.
    to_mode : str
        Name of the mode to transition to.
    transition_type : TransitionType
        The type of transition (e.g., input-triggered, time-based).
    trigger_keywords : List[str], optional
        Keywords or phrases that can trigger the transition (for input-triggered).
    priority : int, optional
        Priority of the rule when multiple rules could apply. Higher numbers = higher priority. Defaults to 1.
    cooldown_seconds : float, optional
        Minimum time in seconds before this rule can trigger again. Defaults to 0.0.
    timeout_seconds : Optional[float], optional
        For time-based transitions, the time in seconds after which to switch modes. Defaults to None.
    context_conditions : Dict, optional
        Conditions based on context that must be met for the transition. Defaults to empty dict.
    """

    from_mode: str
    to_mode: str
    transition_type: TransitionType
    trigger_keywords: List[str] = field(default_factory=list)
    priority: int = 1
    cooldown_seconds: float = 0.0
    timeout_seconds: Optional[float] = None
    context_conditions: Dict = field(default_factory=dict)


@dataclass
class ModeConfig:
    """
    Configuration for a specific mode.
    """

    name: str
    display_name: str
    description: str
    system_prompt_base: str
    hertz: float = 1.0

    timeout_seconds: Optional[float] = None
    remember_locations: bool = False
    save_interactions: bool = False

    lifecycle_hooks: List[LifecycleHook] = field(default_factory=list)
    _raw_lifecycle_hooks: List[Dict] = field(default_factory=list)

    agent_inputs: List[Sensor] = field(default_factory=list)
    cortex_llm: Optional[LLM] = None
    simulators: List[Simulator] = field(default_factory=list)
    agent_actions: List[AgentAction] = field(default_factory=list)
    backgrounds: List[Background] = field(default_factory=list)

    _raw_inputs: List[Dict] = field(default_factory=list)
    _raw_llm: Optional[Dict] = None
    _raw_simulators: List[Dict] = field(default_factory=list)
    _raw_actions: List[Dict] = field(default_factory=list)
    _raw_backgrounds: List[Dict] = field(default_factory=list)

    def to_runtime_config(self, global_config: "ModeSystemConfig") -> RuntimeConfig:
        """
        Convert this mode config to a RuntimeConfig for the cortex.

        Parameters
        ----------
        global_config : ModeSystemConfig
            The global system configuration containing shared settings

        Returns
        -------
        RuntimeConfig
            The runtime configuration for this mode
        """
        if self.cortex_llm is None:
            raise ValueError(f"No LLM configured for mode {self.name}")

        return RuntimeConfig(
            hertz=self.hertz,
            mode=self.name,
            name=f"{global_config.name}_{self.name}",
            system_prompt_base=self.system_prompt_base,
            system_governance=global_config.system_governance,
            system_prompt_examples=global_config.system_prompt_examples,
            agent_inputs=self.agent_inputs,
            cortex_llm=self.cortex_llm,
            simulators=self.simulators,
            agent_actions=self.agent_actions,
            backgrounds=self.backgrounds,
            robot_ip=global_config.robot_ip,
            api_key=global_config.api_key,
            URID=global_config.URID,
            unitree_ethernet=global_config.unitree_ethernet,
        )

    def load_components(self, system_config: "ModeSystemConfig"):
        """
        Load the actual component instances for this mode.

        This method should be called when the mode is activated to ensure
        fresh instances and avoid singleton conflicts between modes.

        Parameters
        ----------
        system_config : ModeSystemConfig
            The global system configuration containing shared settings
        """
        logging.info(f"Loading components for mode: {self.name}")
        _load_mode_components(self, system_config)
        logging.info(f"Components loaded successfully for mode: {self.name}")

    def is_loaded(self) -> bool:
        """
        Check if this mode's components have been loaded.

        Returns
        -------
        bool
            True if components are loaded, False if only raw config is available
        """
        return (
            len(self.agent_inputs) > 0
            or self.cortex_llm is not None
            or len(self.agent_actions) > 0
        )

    async def execute_lifecycle_hooks(
        self, hook_type: LifecycleHookType, context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Execute all lifecycle hooks of the specified type for this mode.

        Parameters
        ----------
        hook_type : LifecycleHookType
            The type of lifecycle hooks to execute
        context : Optional[Dict[str, Any]]
            Context information to pass to the hooks

        Returns
        -------
        bool
            True if all hooks executed successfully, False if any failed
        """
        if context is None:
            context = {}

        context.update(
            {
                "mode_name": self.name,
                "mode_display_name": self.display_name,
                "mode_description": self.description,
            }
        )

        return await execute_lifecycle_hooks(self.lifecycle_hooks, hook_type, context)


@dataclass
class ModeSystemConfig:
    """
    Complete configuration for a mode-aware system.
    """

    # Global settings
    name: str
    default_mode: str
    config_name: str = ""
    allow_manual_switching: bool = True
    mode_memory_enabled: bool = True

    # Global parameters
    api_key: Optional[str] = None
    robot_ip: Optional[str] = None
    URID: Optional[str] = None
    unitree_ethernet: Optional[str] = None
    system_governance: str = ""
    system_prompt_examples: str = ""

    # Default LLM settings if mode doesn't override
    global_cortex_llm: Optional[Dict] = None

    # Global lifecycle hooks (executed for all modes)
    global_lifecycle_hooks: List[LifecycleHook] = field(default_factory=list)
    _raw_global_lifecycle_hooks: List[Dict] = field(default_factory=list)

    # Modes and transition rules
    modes: Dict[str, ModeConfig] = field(default_factory=dict)
    transition_rules: List[TransitionRule] = field(default_factory=list)

    async def execute_global_lifecycle_hooks(
        self, hook_type: LifecycleHookType, context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Execute all global lifecycle hooks of the specified type.

        Parameters
        ----------
        hook_type : LifecycleHookType
            The type of lifecycle hooks to execute
        context : Optional[Dict[str, Any]]
            Context information to pass to the hooks

        Returns
        -------
        bool
            True if all hooks executed successfully, False if any failed
        """
        if context is None:
            context = {}

        context.update({"system_name": self.name, "is_global_hook": True})

        return await execute_lifecycle_hooks(
            self.global_lifecycle_hooks, hook_type, context
        )


def load_mode_config(config_name: str) -> ModeSystemConfig:
    """
    Load a mode-aware configuration from a JSON5 file.

    Parameters
    ----------
    config_name : str
        Name of the configuration file (without .json5 extension)

    Returns
    -------
    ModeSystemConfig
        Parsed mode system configuration
    """
    config_path = os.path.join(
        os.path.dirname(__file__), "../../../config", config_name + ".json5"
    )

    with open(config_path, "r") as f:
        raw_config = json5.load(f)

    g_robot_ip = raw_config.get("robot_ip", None)
    if g_robot_ip is None or g_robot_ip == "" or g_robot_ip == "192.168.0.241":
        logging.warning("No robot ip found in mode config. Checking .env file.")
        backup_key = os.environ.get("ROBOT_IP")
        if backup_key:
            g_robot_ip = backup_key
            logging.info("Found ROBOT_IP in .env file.")

    g_api_key = raw_config.get("api_key", None)
    if g_api_key is None or g_api_key == "" or g_api_key == "openmind_free":
        logging.warning("No API key found in mode config. Checking .env file.")
        backup_key = os.environ.get("OM_API_KEY")
        if backup_key:
            g_api_key = backup_key
            logging.info("Found OM_API_KEY in .env file.")

    g_URID = raw_config.get("URID", "default")
    if g_URID == "default":
        backup_URID = os.environ.get("URID")
        if backup_URID:
            g_URID = backup_URID

    g_ut_eth = raw_config.get("unitree_ethernet", None)
    if g_ut_eth is None or g_ut_eth == "":
        logging.info("No robot hardware ethernet port provided.")
    else:
        load_unitree(g_ut_eth)

    mode_system_config = ModeSystemConfig(
        name=raw_config.get("name", "mode_system"),
        default_mode=raw_config["default_mode"],
        config_name=config_name,
        allow_manual_switching=raw_config.get("allow_manual_switching", True),
        mode_memory_enabled=raw_config.get("mode_memory_enabled", True),
        api_key=g_api_key,
        robot_ip=g_robot_ip,
        URID=g_URID,
        unitree_ethernet=g_ut_eth,
        system_governance=raw_config.get("system_governance", ""),
        system_prompt_examples=raw_config.get("system_prompt_examples", ""),
        global_cortex_llm=raw_config.get("cortex_llm"),
        global_lifecycle_hooks=parse_lifecycle_hooks(
            raw_config.get("global_lifecycle_hooks", [])
        ),
        _raw_global_lifecycle_hooks=raw_config.get("global_lifecycle_hooks", []),
    )

    for mode_name, mode_data in raw_config.get("modes", {}).items():
        mode_config = ModeConfig(
            name=mode_name,
            display_name=mode_data.get("display_name", mode_name),
            description=mode_data.get("description", ""),
            system_prompt_base=mode_data["system_prompt_base"],
            hertz=mode_data.get("hertz", 1.0),
            lifecycle_hooks=parse_lifecycle_hooks(mode_data.get("lifecycle_hooks", [])),
            timeout_seconds=mode_data.get("timeout_seconds"),
            remember_locations=mode_data.get("remember_locations", False),
            save_interactions=mode_data.get("save_interactions", False),
            _raw_inputs=mode_data.get("agent_inputs", []),
            _raw_llm=mode_data.get("cortex_llm"),
            _raw_simulators=mode_data.get("simulators", []),
            _raw_actions=mode_data.get("agent_actions", []),
            _raw_backgrounds=mode_data.get("backgrounds", []),
            _raw_lifecycle_hooks=mode_data.get("lifecycle_hooks", []),
        )

        mode_system_config.modes[mode_name] = mode_config

    for rule_data in raw_config.get("transition_rules", []):
        rule = TransitionRule(
            from_mode=rule_data["from_mode"],
            to_mode=rule_data["to_mode"],
            transition_type=TransitionType(rule_data["transition_type"]),
            trigger_keywords=rule_data.get("trigger_keywords", []),
            priority=rule_data.get("priority", 1),
            cooldown_seconds=rule_data.get("cooldown_seconds", 0.0),
            timeout_seconds=rule_data.get("timeout_seconds"),
            context_conditions=rule_data.get("context_conditions", {}),
        )
        mode_system_config.transition_rules.append(rule)

    return mode_system_config


def _load_mode_components(mode_config: ModeConfig, system_config: ModeSystemConfig):
    """
    Load the actual component instances for a mode.

    Parameters
    ----------
    mode_config : ModeConfig
        The mode configuration to load components for.
    system_config : ModeSystemConfig
        The global system configuration containing shared settings
    """
    g_api_key = system_config.api_key
    g_ut_eth = system_config.unitree_ethernet
    g_URID = system_config.URID
    g_robot_ip = system_config.robot_ip
    g_mode = mode_config.name

    # Load inputs
    mode_config.agent_inputs = [
        load_input(inp["type"])(
            config=SensorConfig(
                **add_meta(
                    inp.get("config", {}),
                    g_api_key,
                    g_ut_eth,
                    g_URID,
                    g_robot_ip,
                    g_mode,
                )
            )
        )
        for inp in mode_config._raw_inputs
    ]

    # Load simulators
    mode_config.simulators = [
        load_simulator(sim["type"])(
            config=SimulatorConfig(
                name=sim["type"],
                **add_meta(
                    sim.get("config", {}),
                    g_api_key,
                    g_ut_eth,
                    g_URID,
                    g_robot_ip,
                    g_mode,
                ),
            )
        )
        for sim in mode_config._raw_simulators
    ]

    # Load actions
    mode_config.agent_actions = [
        load_action(
            {
                **action,
                "config": add_meta(
                    action.get("config", {}),
                    g_api_key,
                    g_ut_eth,
                    g_URID,
                    g_robot_ip,
                    g_mode,
                ),
            }
        )
        for action in mode_config._raw_actions
    ]

    # Load backgrounds
    mode_config.backgrounds = [
        load_background(bg["type"])(
            config=BackgroundConfig(
                **add_meta(
                    bg.get("config", {}),
                    g_api_key,
                    g_ut_eth,
                    g_URID,
                    g_robot_ip,
                    g_mode,
                )
            )
        )
        for bg in mode_config._raw_backgrounds
    ]

    # Load LLM
    llm_config = mode_config._raw_llm or system_config.global_cortex_llm
    if llm_config:
        llm_class = load_llm(llm_config["type"])
        mode_config.cortex_llm = llm_class(
            config=LLMConfig(
                **add_meta(  # type: ignore
                    llm_config.get("config", {}),
                    g_api_key,
                    g_ut_eth,
                    g_URID,
                    g_robot_ip,
                    g_mode,
                )
            ),
            available_actions=mode_config.agent_actions,
        )
    else:
        raise ValueError(f"No LLM configuration found for mode {mode_config.name}")
