import importlib
import json
import os
import sys
from typing import Sequence

from mettagrid.policy.policy import NimMultiAgentPolicy
from mettagrid.policy.policy_env_interface import PolicyEnvInterface

current_dir = os.path.dirname(os.path.abspath(__file__))
bindings_dir = os.path.join(current_dir, "bindings/generated")
if bindings_dir not in sys.path:
    sys.path.append(bindings_dir)

_na = None


def _nim_agents():
    global _na
    if _na is None:
        try:
            _na = importlib.import_module("nim_agents")
        except (ImportError, OSError):
            # Build the Nim bindings on demand rather than requiring them at import time.
            # This keeps policy discovery cheap while still making `metta://policy/*nim*`
            # URIs usable anywhere the build toolchain is available.
            from cogames_agents.policy.nim_agents.build import build_nim  # noqa: PLC0415

            build_nim()
            _na = importlib.import_module("nim_agents")
    return _na


class _NimAgentsProxy:
    def __getattr__(self, name: str):
        return getattr(_nim_agents(), name)


# Kept for callers/tests that expect `agents.na.<binding>`, but loaded lazily so importing
# this module doesn't require Nim bindings to be present.
na = _NimAgentsProxy()


def start_measure():
    _nim_agents().start_measure()


def end_measure():
    _nim_agents().end_measure()


class ThinkyAgentsMultiPolicy(NimMultiAgentPolicy):
    short_names = ["thinky"]

    def __init__(self, policy_env_info: PolicyEnvInterface, agent_ids: Sequence[int] | None = None):
        super().__init__(
            policy_env_info,
            nim_policy_factory=_nim_agents().ThinkyPolicy,
            agent_ids=agent_ids,
        )


class RandomAgentsMultiPolicy(NimMultiAgentPolicy):
    short_names = ["nim_random"]

    def __init__(self, policy_env_info: PolicyEnvInterface, agent_ids: Sequence[int] | None = None):
        super().__init__(
            policy_env_info,
            nim_policy_factory=_nim_agents().RandomPolicy,
            agent_ids=agent_ids,
        )


class RaceCarAgentsMultiPolicy(NimMultiAgentPolicy):
    short_names = ["race_car"]

    def __init__(self, policy_env_info: PolicyEnvInterface, agent_ids: Sequence[int] | None = None):
        super().__init__(
            policy_env_info,
            nim_policy_factory=_nim_agents().RaceCarPolicy,
            agent_ids=agent_ids,
        )


class CogsguardAgentsMultiPolicy(NimMultiAgentPolicy):
    short_names = ["role_nim"]

    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        agent_ids: Sequence[int] | None = None,
        **_: object,
    ):
        super().__init__(
            policy_env_info,
            nim_policy_factory=_nim_agents().CogsguardPolicy,
            agent_ids=agent_ids,
        )


class CogsguardAlignAllAgentsMultiPolicy(NimMultiAgentPolicy):
    short_names = ["alignall"]

    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        agent_ids: Sequence[int] | None = None,
        **_: object,
    ):
        super().__init__(
            policy_env_info,
            nim_policy_factory=_nim_agents().CogsguardAlignAllPolicy,
            agent_ids=agent_ids,
        )


class NlankyAgentsMultiPolicy(NimMultiAgentPolicy):
    short_names = ["nlanky"]

    @staticmethod
    def _coerce_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
        if isinstance(value, str):
            v = value.strip().lower()
            if v in {"1", "true", "t", "yes", "y", "on"}:
                return True
            if v in {"0", "false", "f", "no", "n", "off", ""}:
                return False
        return bool(value)

    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        device: str = "cpu",
        agent_ids: Sequence[int] | None = None,
        miner: int | str = -1,
        scout: int | str = 0,
        aligner: int | str = -1,
        scrambler: int | str = -1,
        stem: int | str = 0,
        trace: int | str = 0,
        trace_level: int | str = 1,
        trace_agent: int | str = -1,
        bio: int | str = 0,
        stats: int | str = 0,
        disable_role_switching: bool | int | str = 0,
        **_: object,
    ):
        # `cogames play -p "... kw.foo=1"` passes strings; be robust and coerce.
        _ = int(bio)
        _ = int(stats)
        miner_i = int(miner)
        scout_i = int(scout)
        aligner_i = int(aligner)
        scrambler_i = int(scrambler)
        stem_i = int(stem)
        trace_i = int(trace)
        trace_level_i = int(trace_level)
        trace_agent_i = int(trace_agent)
        disable_role_switching_b = self._coerce_bool(disable_role_switching)

        # Don't rely on newer mettagrid APIs (some runners don't support passing
        # `init_config_json` into NimMultiAgentPolicy). Instead, wrap the
        # env JSON provided by NimMultiAgentPolicy into Nlanky's expected shape.
        def _policy_factory(env_json: str):
            env = json.loads(env_json)
            init_config_json = json.dumps(
                {
                    "env": env,
                    "nlanky": {
                        "miner": miner_i,
                        "scout": scout_i,
                        "aligner": aligner_i,
                        "scrambler": scrambler_i,
                        "stem": stem_i,
                        "trace": trace_i,
                        "traceLevel": trace_level_i,
                        "traceAgent": trace_agent_i,
                        "disableRoleSwitching": disable_role_switching_b,
                    },
                }
            )
            return _nim_agents().NlankyPolicy(init_config_json)

        super().__init__(
            policy_env_info,
            nim_policy_factory=_policy_factory,
            agent_ids=agent_ids,
            device=device,
        )
