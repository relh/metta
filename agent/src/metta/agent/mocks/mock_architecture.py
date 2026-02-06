from pydantic import Field

from metta.agent.mocks.mock_agent import MockAgent
from metta.agent.policy import PolicyArchitecture
from mettagrid.base_config import Config


class MockArchitecture(PolicyArchitecture):
    class_path: str = "metta.agent.mocks.mock_agent.MockAgent"
    action_probs_config: Config = Field(default_factory=Config)

    def make_policy(self, policy_env_info):
        return MockAgent()
