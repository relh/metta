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

na = importlib.import_module("nim_agents")


def start_measure():
    na.start_measure()


def end_measure():
    na.end_measure()


class ThinkyAgentsMultiPolicy(NimMultiAgentPolicy):
    short_names = ["thinky"]

    def __init__(self, policy_env_info: PolicyEnvInterface, agent_ids: Sequence[int] | None = None):
        super().__init__(
            policy_env_info,
            nim_policy_factory=na.ThinkyPolicy,
            agent_ids=agent_ids,
        )


class RandomAgentsMultiPolicy(NimMultiAgentPolicy):
    short_names = ["nim_random"]

    def __init__(self, policy_env_info: PolicyEnvInterface, agent_ids: Sequence[int] | None = None):
        super().__init__(
            policy_env_info,
            nim_policy_factory=na.RandomPolicy,
            agent_ids=agent_ids,
        )


class RaceCarAgentsMultiPolicy(NimMultiAgentPolicy):
    short_names = ["race_car"]

    def __init__(self, policy_env_info: PolicyEnvInterface, agent_ids: Sequence[int] | None = None):
        super().__init__(
            policy_env_info,
            nim_policy_factory=na.RaceCarPolicy,
            agent_ids=agent_ids,
        )


class CogsguardAgentsMultiPolicy(NimMultiAgentPolicy):
    short_names = ["role"]

    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        agent_ids: Sequence[int] | None = None,
        **_: object,
    ):
        super().__init__(
            policy_env_info,
            nim_policy_factory=na.CogsguardPolicy,
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
            nim_policy_factory=na.CogsguardAlignAllPolicy,
            agent_ids=agent_ids,
        )


class PlankyAgentsMultiPolicy(NimMultiAgentPolicy):
    short_names = ["planky_nim", "nlanky"]

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
        agent_ids: Sequence[int] | None = None,
        miner: int | str = -1,
        scout: int | str = 0,
        aligner: int | str = -1,
        scrambler: int | str = -1,
        stem: int | str = 0,
        trace: int | str = 0,
        trace_level: int | str = 1,
        trace_agent: int | str = -1,
        disable_role_switching: bool | int | str = 0,
        **_: object,
    ):
        # `cogames play -p "... kw.foo=1"` passes strings; be robust and coerce.
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
        # env JSON provided by NimMultiAgentPolicy into Planky's expected shape.
        def _policy_factory(env_json: str):
            env = json.loads(env_json)
            init_config_json = json.dumps(
                {
                    "env": env,
                    "planky": {
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
            return na.PlankyPolicy(init_config_json)

        super().__init__(
            policy_env_info,
            nim_policy_factory=_policy_factory,
            agent_ids=agent_ids,
        )
