from __future__ import annotations

from cortex import RoutedAdapterConfig
from cortex.rl.feature_extractors import (
    BoxCNNFeatureExtractorConfig,
    TokenMLPFeatureExtractorConfig,
    TokenPerceiverFeatureExtractorConfig,
)
from cortex.stacks import build_cortex_auto_config

from metta.agent.policies.default import DefaultPolicyConfig
from metta.agent.policy import PolicyArchitecture


def test_core_policy_architecture_to_spec_round_trip_with_routed_adapter() -> None:
    cfg = DefaultPolicyConfig(cortex_routed_adapter=RoutedAdapterConfig(num_slots=8, rank=2))

    spec = cfg.to_spec()
    assert isinstance(spec, str) and len(spec) > 0

    reconstructed = PolicyArchitecture.from_spec(spec)
    assert isinstance(reconstructed, DefaultPolicyConfig)
    assert reconstructed.model_dump(mode="json") == cfg.model_dump(mode="json")


def test_core_policy_architecture_to_spec_round_trip_with_token_mlp_extractor() -> None:
    cfg = DefaultPolicyConfig(
        feature_extractor=TokenMLPFeatureExtractorConfig(output_dim=96, hidden_features=[128, 128])
    )

    reconstructed = PolicyArchitecture.from_spec(cfg.to_spec())
    assert isinstance(reconstructed, DefaultPolicyConfig)
    assert reconstructed.model_dump(mode="json") == cfg.model_dump(mode="json")


def test_core_policy_architecture_to_spec_round_trip_with_box_cnn_extractor() -> None:
    cfg = DefaultPolicyConfig(feature_extractor=BoxCNNFeatureExtractorConfig(output_dim=96, hidden_dim=192))

    reconstructed = PolicyArchitecture.from_spec(cfg.to_spec())
    assert isinstance(reconstructed, DefaultPolicyConfig)
    assert reconstructed.model_dump(mode="json") == cfg.model_dump(mode="json")


def test_core_policy_architecture_to_spec_round_trip_with_token_perceiver_extractor() -> None:
    cfg = DefaultPolicyConfig(
        feature_extractor=TokenPerceiverFeatureExtractorConfig(
            latent_dim=96,
            num_latents=8,
            num_heads=2,
            num_layers=1,
        )
    )

    reconstructed = PolicyArchitecture.from_spec(cfg.to_spec())
    assert isinstance(reconstructed, DefaultPolicyConfig)
    assert reconstructed.model_dump(mode="json") == cfg.model_dump(mode="json")


def test_core_policy_architecture_to_spec_round_trip_with_cortex_custom_map() -> None:
    cfg = DefaultPolicyConfig(cortex_custom_map={})

    reconstructed = PolicyArchitecture.from_spec(cfg.to_spec())
    assert isinstance(reconstructed, DefaultPolicyConfig)
    assert reconstructed.model_dump(mode="json") == cfg.model_dump(mode="json")


def test_core_policy_architecture_to_spec_round_trip_with_explicit_cortex_stack_cfg() -> None:
    cfg = DefaultPolicyConfig(
        feature_extractor=TokenPerceiverFeatureExtractorConfig(
            latent_dim=96,
            num_latents=8,
            num_heads=2,
            num_layers=1,
        ),
        cortex_stack_cfg=build_cortex_auto_config(d_hidden=96),
    )

    reconstructed = PolicyArchitecture.from_spec(cfg.to_spec())
    assert isinstance(reconstructed, DefaultPolicyConfig)
    assert reconstructed.model_dump(mode="json") == cfg.model_dump(mode="json")
