from __future__ import annotations

from collections.abc import Iterable

import pytest

from mettagrid.mettagrid_c import PackedCoordinate
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.simulator import AgentObservation, ObservationToken


@pytest.fixture
def cogsguard_env_info() -> PolicyEnvInterface:
    make_cogsguard_mission = pytest.importorskip("cogames.cogs_vs_clips.missions").make_cogsguard_mission
    mission = make_cogsguard_mission(num_agents=4, max_steps=50)
    return PolicyEnvInterface.from_mg_cfg(mission.make_env())


def _feature_by_name(policy_env_info: PolicyEnvInterface, feature_name: str):
    for feature in policy_env_info.obs_features:
        if feature.name == feature_name:
            return feature
    raise KeyError(f"Unknown feature: {feature_name}")


def _make_token(
    policy_env_info: PolicyEnvInterface,
    feature_name: str,
    value: int,
    *,
    row: int | None = None,
    col: int | None = None,
    is_global: bool = False,
) -> ObservationToken:
    feature = _feature_by_name(policy_env_info, feature_name)
    if is_global:
        packed = PackedCoordinate.GLOBAL_LOCATION
    else:
        if row is None or col is None:
            raise ValueError("row and col are required for spatial tokens")
        packed = PackedCoordinate.pack(row, col)
    return ObservationToken(feature=feature, value=value, raw_token=(packed, feature.id, value))


def _make_tag_token(
    policy_env_info: PolicyEnvInterface,
    tag_name: str,
    *,
    row: int,
    col: int,
) -> ObservationToken:
    return _make_token(
        policy_env_info,
        "tag",
        policy_env_info.tags.index(tag_name),
        row=row,
        col=col,
    )


def _make_observation(
    policy_env_info: PolicyEnvInterface,
    tokens: Iterable[ObservationToken],
    *,
    agent_id: int = 0,
) -> AgentObservation:
    return AgentObservation(agent_id=agent_id, tokens=list(tokens))


@pytest.fixture
def make_token():
    return _make_token


@pytest.fixture
def make_tag_token():
    return _make_tag_token


@pytest.fixture
def make_observation():
    return _make_observation
