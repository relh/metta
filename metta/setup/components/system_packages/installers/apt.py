import shutil
import subprocess

from metta.setup.components.system_packages.installers.base import PackageInstaller
from metta.setup.components.system_packages.types import AptPackageConfig
from metta.setup.utils import info, warning


class AptInstaller(PackageInstaller[AptPackageConfig]):
    def __init__(self):
        self._apt_updated = False

    @property
    def name(self) -> str:
        return "apt"

    def is_available(self) -> bool:
        return shutil.which("apt-get") is not None

    def _get_installed_packages(self) -> list[str]:
        result = subprocess.run(["dpkg", "--get-selections"], text=True, check=True, capture_output=True)
        lines = result.stdout.strip().split("\n")
        return [line.split("\t")[0] for line in lines if "\tinstall" in line]

    def _is_package_available(self, package: str) -> bool:
        result = subprocess.run(["apt-cache", "show", package], capture_output=True, check=False)
        return result.returncode == 0

    def _ensure_updated(self) -> None:
        if not self._apt_updated:
            info("Updating apt package list...")
            subprocess.run(["sudo", "apt-get", "update"], check=True, capture_output=False)
            self._apt_updated = True

    def check_installed(self, packages: list[AptPackageConfig]) -> bool:
        installed = self._get_installed_packages()
        package_names = [p.name for p in packages]
        to_install = [pkg for pkg in package_names if pkg not in installed]
        return len(to_install) == 0

    def install(self, packages: list[AptPackageConfig]) -> None:
        self._ensure_updated()

        installed = self._get_installed_packages()
        to_install = [p.name for p in packages if p.name not in installed]
        if not to_install:
            return

        available = [pkg for pkg in to_install if self._is_package_available(pkg)]
        skipped = set(to_install) - set(available)
        if skipped:
            warning(f"Skipping packages not available in apt: {', '.join(sorted(skipped))}")

        if available:
            info(f"Installing {', '.join(available)}...")
            result = subprocess.run(["sudo", "apt-get", "install", "-y", *available], check=False, capture_output=False)
            if result.returncode != 0:
                warning("Batch install failed, falling back to individual package installation...")
                failed = []
                for pkg in available:
                    r = subprocess.run(["sudo", "apt-get", "install", "-y", pkg], check=False, capture_output=True)
                    if r.returncode != 0:
                        failed.append(pkg)
                if failed:
                    warning(f"Failed to install: {', '.join(failed)}")
