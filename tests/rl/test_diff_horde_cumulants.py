import pytest
import torch
from tensordict import TensorDict

from metta.rl.diff_horde.cumulants import DiffHordeCumulantExtractor, DiffHordeCumulantsConfig
from mettagrid.config.id_map import ObservationFeatureSpec
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


def _policy_env_info() -> PolicyEnvInterface:
    return PolicyEnvInterface(
        obs_features=[
            ObservationFeatureSpec(id=7, name="inv:hp", normalization=100.0),
            ObservationFeatureSpec(id=11, name="inv:ore", normalization=50.0),
        ],
        tags=[],
        action_names=["noop"],
        vibe_action_names=[],
        move_energy_cost=None,
        num_agents=2,
        observation_shape=(4, 3),
        egocentric_shape=(3, 3),
    )


def test_cumulants_config_normalizes_name_mapping_and_counts_features() -> None:
    cfg = DiffHordeCumulantsConfig.model_validate(
        {
            "hp": {"kind": "env_obs_feature", "feature": "inv:hp", "normalize": True},
            "territory_now": {"kind": "info_scalar", "key": "env_team/cogs/aligned.junction"},
            "core2": {"kind": "td_key", "key": "core", "slice": "0:2"},
        }
    )

    assert [spec.name for spec in cfg.specs] == ["hp", "territory_now", "core2"]
    assert cfg.num_cumulants == 4
    assert cfg.required_td_keys() == {"env_obs", "core"}
    assert cfg.required_info_keys() == {"env_team/cogs/aligned.junction"}


def test_cumulant_extractor_combines_env_info_and_td_sources() -> None:
    cfg = DiffHordeCumulantsConfig.model_validate(
        {
            "hp": {"kind": "env_obs_feature", "feature": "inv:hp", "reduce": "mean", "normalize": True},
            "territory_now": {"kind": "info_scalar", "key": "env_team/cogs/aligned.junction"},
            "core2": {"kind": "td_key", "key": "core", "slice": "1:3"},
        }
    )
    extractor = DiffHordeCumulantExtractor(cfg, _policy_env_info())

    env_obs = torch.tensor(
        [
            [[0, 7, 10], [1, 7, 30], [255, 255, 255], [2, 1, 5]],
            [[0, 11, 9], [1, 11, 4], [255, 255, 255], [255, 255, 255]],
        ],
        dtype=torch.uint8,
    )
    td = TensorDict(
        {
            "env_obs": env_obs,
            "core": torch.tensor([[9.0, 8.0, 7.0], [1.0, 2.0, 3.0]], dtype=torch.float32),
            "env_info": TensorDict(
                {
                    "env_team/cogs/aligned.junction": torch.tensor([1.5, 2.5], dtype=torch.float32),
                },
                batch_size=[2],
            ),
        },
        batch_size=[2],
    )

    out = extractor(td)

    expected = torch.tensor(
        [
            [0.2, 1.5, 8.0, 7.0],
            [0.0, 2.5, 2.0, 3.0],
        ],
        dtype=torch.float32,
    )
    torch.testing.assert_close(out, expected)


def test_cumulant_extractor_raises_when_info_key_missing() -> None:
    cfg = DiffHordeCumulantsConfig.model_validate(
        [{"kind": "info_scalar", "name": "territory_now", "key": "env_team/cogs/aligned.junction"}]
    )
    extractor = DiffHordeCumulantExtractor(cfg, _policy_env_info())
    td = TensorDict({"env_info": TensorDict({}, batch_size=[2])}, batch_size=[2])

    with pytest.raises(RuntimeError, match="Missing env_info key"):
        extractor(td)


def test_cumulant_extractor_raises_for_unknown_feature_name() -> None:
    cfg = DiffHordeCumulantsConfig.model_validate(
        [{"kind": "env_obs_feature", "name": "mystery", "feature": "inv:missing"}]
    )

    with pytest.raises(RuntimeError, match="Unknown obs feature name"):
        DiffHordeCumulantExtractor(cfg, _policy_env_info())


def test_td_key_whole_vector_auto_sizes_from_extracted_shape() -> None:
    cfg = DiffHordeCumulantsConfig.model_validate({"core_all": {"kind": "td_key", "key": "core"}})
    with pytest.raises(ValueError, match="Unresolved td_key cumulant size"):
        _ = cfg.num_cumulants

    extractor = DiffHordeCumulantExtractor(cfg, _policy_env_info())
    td = TensorDict(
        {
            "core": torch.tensor(
                [
                    [[1.0, 2.0], [3.0, 4.0]],
                    [[5.0, 6.0], [7.0, 8.0]],
                ],
                dtype=torch.float32,
            )
        },
        batch_size=[2],
    )

    out = extractor(td)
    expected = torch.tensor(
        [
            [1.0, 2.0, 3.0, 4.0],
            [5.0, 6.0, 7.0, 8.0],
        ],
        dtype=torch.float32,
    )
    torch.testing.assert_close(out, expected)
    assert cfg.specs[0].size == 4
    assert cfg.num_cumulants == 4
