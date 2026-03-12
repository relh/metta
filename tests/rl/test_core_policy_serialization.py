from __future__ import annotations

from cortex import AxonCellConfig, RoutedAdapterConfig
from cortex.rl.feature_extractors import (
    BoxCNNFeatureExtractorConfig,
    TokenMLPFeatureExtractorConfig,
    TokenPerceiverFeatureExtractorConfig,
)
from cortex.stacks import build_cortex_auto_config

from metta.agent.components.drama.config import DramaWorldModelConfig
from metta.agent.policies.default import DefaultPolicyConfig
from metta.agent.policies.drama_policy import DramaPolicyConfig
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


def test_core_policy_architecture_to_spec_round_trip_with_cortex_cells() -> None:
    cfg = DefaultPolicyConfig(cortex_cells=[AxonCellConfig()])

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


def test_core_policy_architecture_to_spec_round_trip_with_drama_policy() -> None:
    cfg = DramaPolicyConfig()

    reconstructed = PolicyArchitecture.from_spec(cfg.to_spec())
    assert isinstance(reconstructed, DramaPolicyConfig)
    assert reconstructed.model_dump(mode="json") == cfg.model_dump(mode="json")


def test_drama_world_model_config_has_no_dead_field_shims() -> None:
    assert "pool" not in DramaWorldModelConfig.model_fields
    assert "use_reward_token" not in DramaWorldModelConfig.model_fields
    assert "use_reset_token" not in DramaWorldModelConfig.model_fields


def test_drama_world_model_config_accepts_legacy_payload_and_normalizes_none() -> None:
    cfg = DramaWorldModelConfig.model_validate(
        {
            "pool": "mean",
            "use_reward_token": False,
            "use_reset_token": False,
            "ssm_cfg": None,
            "attn_layer_idx": None,
            "attn_cfg": None,
            "pff_cfg": None,
        }
    )

    assert cfg.ssm_cfg == {}
    assert cfg.attn_layer_idx == []
    assert cfg.attn_cfg == {}
    assert cfg.pff_cfg == {}
