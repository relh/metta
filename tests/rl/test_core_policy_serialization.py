from __future__ import annotations

from cortex import RoutedAdapterConfig
from cortex.rl.feature_extractors import (
    BoxCNNFeatureExtractorConfig,
    TokenMLPFeatureExtractorConfig,
    TokenPerceiverFeatureExtractorConfig,
)

from metta.agent.policies.core_policy import CorePolicyConfig
from metta.agent.policy import PolicyArchitecture


def test_core_policy_architecture_to_spec_round_trip_with_routed_adapter() -> None:
    cfg = CorePolicyConfig(cortex_routed_adapter=RoutedAdapterConfig(num_slots=8, rank=2))

    spec = cfg.to_spec()
    assert isinstance(spec, str) and len(spec) > 0

    reconstructed = PolicyArchitecture.from_spec(spec)
    assert isinstance(reconstructed, CorePolicyConfig)
    assert reconstructed.model_dump(mode="json") == cfg.model_dump(mode="json")


def test_core_policy_architecture_to_spec_round_trip_with_token_mlp_extractor() -> None:
    cfg = CorePolicyConfig(feature_extractor=TokenMLPFeatureExtractorConfig(output_dim=96, hidden_features=[128, 128]))

    reconstructed = PolicyArchitecture.from_spec(cfg.to_spec())
    assert isinstance(reconstructed, CorePolicyConfig)
    assert reconstructed.model_dump(mode="json") == cfg.model_dump(mode="json")


def test_core_policy_architecture_to_spec_round_trip_with_box_cnn_extractor() -> None:
    cfg = CorePolicyConfig(feature_extractor=BoxCNNFeatureExtractorConfig(output_dim=96, hidden_dim=192))

    reconstructed = PolicyArchitecture.from_spec(cfg.to_spec())
    assert isinstance(reconstructed, CorePolicyConfig)
    assert reconstructed.model_dump(mode="json") == cfg.model_dump(mode="json")


def test_core_policy_architecture_to_spec_round_trip_with_token_perceiver_extractor() -> None:
    cfg = CorePolicyConfig(
        feature_extractor=TokenPerceiverFeatureExtractorConfig(
            latent_dim=96,
            num_latents=8,
            num_heads=2,
            num_layers=1,
        )
    )

    reconstructed = PolicyArchitecture.from_spec(cfg.to_spec())
    assert isinstance(reconstructed, CorePolicyConfig)
    assert reconstructed.model_dump(mode="json") == cfg.model_dump(mode="json")
