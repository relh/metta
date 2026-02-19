from unittest.mock import MagicMock

from metta.setup.tools.sandbox.ec2 import (
    build_bake_user_data,
    build_launch_user_data,
    build_user_data,
    get_instance_by_name,
    launch_instance,
    resolve_baked_ami,
)


def _make_ec2_client(instances: list[dict]) -> MagicMock:
    client = MagicMock()
    client.describe_instances.return_value = {"Reservations": [{"Instances": instances}] if instances else []}
    return client


def _make_instance(instance_id: str, name: str, user: str, state: str = "running", ip: str = "1.2.3.4") -> dict:
    return {
        "InstanceId": instance_id,
        "State": {"Name": state},
        "PublicIpAddress": ip,
        "InstanceType": "m6i.2xlarge",
        "LaunchTime": "2026-01-01T00:00:00Z",
        "Tags": [
            {"Key": "Name", "Value": name},
            {"Key": "metta:user", "Value": user},
            {"Key": "metta:type", "Value": "aicode"},
            {"Key": "metta:git-ref", "Value": "main"},
        ],
    }


def test_get_instance_by_name_scopes_to_user():
    ec2 = _make_ec2_client([_make_instance("i-abc", "alice-sandbox-1", "alice")])
    get_instance_by_name(ec2, "alice-sandbox-1", username="bob")
    filters = ec2.describe_instances.call_args[1]["Filters"]
    user_filters = [f for f in filters if f["Name"] == "tag:metta:user"]
    assert len(user_filters) == 1
    assert user_filters[0]["Values"] == ["bob"]


def test_get_instance_by_name_returns_own_instance():
    ec2 = _make_ec2_client([_make_instance("i-abc", "alice-sandbox-1", "alice")])
    result = get_instance_by_name(ec2, "alice-sandbox-1", username="alice")
    assert result is not None
    assert result.instance_id == "i-abc"


def test_launch_instance_uses_provided_image_id():
    ec2 = MagicMock()
    ec2.run_instances.return_value = {"Instances": [{"InstanceId": "i-new"}]}
    launch_instance(
        ec2,
        name="test-box",
        instance_type="m6i.2xlarge",
        key_name="test-key",
        sg_id="sg-123",
        user_data="#!/bin/bash",
        username="alice",
        git_ref="main",
        image_id="ami-custom123",
        repo="Metta-AI/metta",
    )
    call_kwargs = ec2.run_instances.call_args[1]
    assert call_kwargs["ImageId"] == "ami-custom123"


def test_launch_instance_tags_repo():
    ec2 = MagicMock()
    ec2.run_instances.return_value = {"Instances": [{"InstanceId": "i-new"}]}
    launch_instance(
        ec2,
        name="test-box",
        instance_type="m6i.2xlarge",
        key_name="test-key",
        sg_id="sg-123",
        user_data="#!/bin/bash",
        username="alice",
        git_ref="main",
        image_id="ami-custom123",
        repo="some-org/other-repo",
    )
    tags = ec2.run_instances.call_args[1]["TagSpecifications"][0]["Tags"]
    repo_tags = [t for t in tags if t["Key"] == "metta:repo"]
    assert len(repo_tags) == 1
    assert repo_tags[0]["Value"] == "some-org/other-repo"


def test_build_user_data_installs_coding_tools():
    script = build_user_data("fake-pat", "main", "some-org/other-repo")
    assert "@anthropic-ai/claude-code" in script
    assert "@openai/codex" in script
    assert "@google/gemini-cli" in script
    assert "gastown" in script
    assert "beads" in script
    assert "setup_22.x" in script


def test_build_user_data_metta_repo_runs_install():
    script = build_user_data("fake-pat", "main", "Metta-AI/metta")
    assert "install.sh --profile softmax-docker --non-interactive" in script
    assert "uv sync" in script


def test_build_user_data_non_metta_repo_skips_install():
    script = build_user_data("fake-pat", "main", "some-org/other-repo")
    assert "install.sh" not in script
    assert "/home/ubuntu/other-repo" in script


def test_build_bake_user_data_installs_tools_and_metta():
    script = build_bake_user_data("fake-pat")
    assert "@anthropic-ai/claude-code" in script
    assert "@openai/codex" in script
    assert "@google/gemini-cli" in script
    assert "gastown" in script
    assert "beads" in script
    assert "setup_22.x" in script
    assert "gt install ~/gt --git" in script
    assert "Metta-AI/metta" in script
    assert "install.sh --profile softmax-docker --non-interactive" in script
    assert "uv sync" in script
    assert "git-credentials" not in script
    assert "remote set-url origin https://github.com/Metta-AI/metta.git" in script


def test_build_launch_user_data_metta_fetches_ref():
    script = build_launch_user_data("fake-pat", "my-branch", "Metta-AI/metta")
    assert "git fetch origin" in script
    assert "remote set-url" in script
    assert "uv sync" in script
    assert "git clone --depth" not in script
    assert "install.sh" not in script


def test_build_launch_user_data_non_metta_clones():
    script = build_launch_user_data("fake-pat", "main", "some-org/other-repo")
    assert "git clone --depth" in script
    assert "git-credentials" in script
    assert "gt rig add" in script
    assert "setup_22.x" not in script
    assert "@anthropic-ai/claude-code" not in script
    assert "go1.24.2" not in script


def test_resolve_baked_ami_returns_latest():
    ec2 = MagicMock()
    ec2.describe_images.return_value = {
        "Images": [
            {"ImageId": "ami-old", "CreationDate": "2026-01-01T00:00:00Z"},
            {"ImageId": "ami-new", "CreationDate": "2026-02-01T00:00:00Z"},
        ]
    }
    result = resolve_baked_ami(ec2)
    assert result == "ami-new"
    filters = ec2.describe_images.call_args[1]["Filters"]
    type_filter = [f for f in filters if f["Name"] == "tag:metta:type"]
    assert type_filter[0]["Values"] == ["aicode-baked"]


def test_resolve_baked_ami_returns_none_when_empty():
    ec2 = MagicMock()
    ec2.describe_images.return_value = {"Images": []}
    result = resolve_baked_ami(ec2)
    assert result is None


def test_build_launch_user_data_writes_gh_config():
    script = build_launch_user_data("fake-pat", "main", "Metta-AI/metta")
    assert "hosts.yml" in script
    assert "oauth_token" in script
    assert "gh auth login" not in script


def test_build_launch_user_data_cleans_remote_url():
    for repo in ("Metta-AI/metta", "some-org/other-repo"):
        script = build_launch_user_data("fake-pat", "main", repo)
        lines = script.split("\n")
        set_url_lines = [line for line in lines if "remote set-url origin" in line]
        last_set_url = set_url_lines[-1]
        assert "x-access-token" not in last_set_url
        assert "https://github.com/" in last_set_url


def test_gastown_rig_uses_clean_url():
    script = build_launch_user_data("fake-pat", "main", "Metta-AI/metta")
    rig_lines = [line for line in script.split("\n") if "gt rig add" in line]
    assert len(rig_lines) == 1
    assert "x-access-token" not in rig_lines[0]
    assert "https://github.com/" in rig_lines[0]
