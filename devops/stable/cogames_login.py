# Locally resolves to repo cogames, on GHA from PyPi package
from cogames.auth import BaseCLIAuthenticator


class CogamesAuthenticator(BaseCLIAuthenticator):
    """CLI Authenticator for Observatory, storing tokens in cogames.yaml."""

    def __init__(self):
        super().__init__(
            token_file_name="cogames.yaml",
            token_storage_key="login_tokens",
        )
