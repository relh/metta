import shutil
import subprocess
from pathlib import Path

import typer

from metta.common.util.fs import get_repo_root
from metta.setup.utils import error, info, success

app = typer.Typer(
    help="MettaGrid Nim test runner",
    invoke_without_command=True,
)

# Nimby uses a global lock directory at ~/.nimby/nimbylock (created atomically via mkdir).
# When nimby crashes, the lock can be left behind and subsequent nimby invocations fail.
_NIMBY_LOCK = Path.home() / ".nimby" / "nimbylock"


def _cleanup_nimby_lock() -> None:
    if not _NIMBY_LOCK.exists():
        return
    info(f"Removing nimby lock left behind by crashed process: {_NIMBY_LOCK}")
    shutil.rmtree(_NIMBY_LOCK, ignore_errors=True)


@app.callback()
def command() -> None:
    repo_root = get_repo_root()
    mettascope_dir = repo_root / "packages" / "mettagrid" / "nim" / "mettascope"
    lock_file = mettascope_dir / "nimby.lock"

    # Install Nim dependencies before running tests
    info("Installing Nim dependencies...")
    sync_cmd = ["nimby", "sync", "-g", str(lock_file)]
    _cleanup_nimby_lock()
    exit_code = subprocess.run(
        sync_cmd,
        check=False,
        cwd=repo_root.parent,  # nimby sync expects to run from parent of repo
    ).returncode
    if exit_code != 0:
        # `nimby sync` can fail if the cached global packages directory is corrupted.
        # Clearing the cache and retrying is cheaper than failing the entire CI job.
        pkgs_dir = Path.home() / ".nimby" / "pkgs"
        if pkgs_dir.exists():
            info(f"nimby sync failed; removing cached packages at {pkgs_dir} and retrying...")
            shutil.rmtree(pkgs_dir)
        _cleanup_nimby_lock()
        exit_code = subprocess.run(
            sync_cmd,
            check=False,
            cwd=repo_root.parent,
        ).returncode
    if exit_code != 0:
        error("Failed to install Nim dependencies!")
        raise typer.Exit(exit_code)
    success("Nim dependencies installed!")

    test_files = (mettascope_dir / "tests").glob("test_*.nim")
    for test_file in test_files:
        info(f"Running {test_file}...")
        exit_code = subprocess.run(["nim", "r", str(test_file)], check=False).returncode
        if exit_code != 0:
            error(f"Nim {test_file} failed!")
            raise typer.Exit(exit_code)
        success(f"Nim {test_file} completed successfully!")
