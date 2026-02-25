from metta.app_backend.models.tournament import MettagridEnvConfig


def test_env_config_has_name_and_compat_version_fields():
    config = MettagridEnvConfig(
        config_hash="abc123",
        config={"game": {}},
        name="test_env",
        compat_version="0.13",
        git_commit="abc123def",
        num_agents=5,
    )
    assert config.name == "test_env"
    assert config.compat_version == "0.13"
    assert config.git_commit == "abc123def"
    assert config.num_agents == 5


def test_env_config_new_fields_default_to_none():
    config = MettagridEnvConfig(config_hash="abc123", config={"game": {}})
    assert config.name is None
    assert config.compat_version is None
    assert config.git_commit is None
    assert config.num_agents is None
