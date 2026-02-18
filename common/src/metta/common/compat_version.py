from packaging.version import InvalidVersion, Version

from metta.common.util.fs import get_repo_root


def get_compat_version() -> str:
    path = get_repo_root() / "COMPAT_VERSION"
    return path.read_text().strip()


def parse_compat_version(version_string: str) -> str | None:
    try:
        v = Version(version_string)
    except InvalidVersion:
        return None
    return f"{v.major}.{v.minor}"
