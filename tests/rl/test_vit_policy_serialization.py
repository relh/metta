from __future__ import annotations

from cortex import RoutedAdapterConfig

from metta.agent.policies.vit import ViTDefaultConfig
from metta.agent.policy import PolicyArchitecture


def test_vit_architecture_to_spec_round_trip_with_routed_adapter() -> None:
    cfg = ViTDefaultConfig(core_routed_adapter=RoutedAdapterConfig(num_slots=8, rank=2))

    spec = cfg.to_spec()
    assert isinstance(spec, str) and len(spec) > 0

    reconstructed = PolicyArchitecture.from_spec(spec)
    assert isinstance(reconstructed, ViTDefaultConfig)
    assert reconstructed.model_dump(mode="json") == cfg.model_dump(mode="json")
