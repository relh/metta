"""Local Kubernetes runtime management for Observatory.

This module provides dual-runtime support for local Kubernetes development:
- OrbStack: For direct macOS development (simpler, preferred when available)
- k3d: For devcontainer/Linux development (k3s-in-Docker)

=============================================================================
ARCHITECTURE OVERVIEW
=============================================================================

Observatory needs Kubernetes to run job pods (policy evaluation). The challenge
is supporting two different development scenarios:

1. DIRECT MAC DEVELOPMENT (OrbStack)
   Developer runs `metta dev` directly on macOS.
   OrbStack provides K8s and shares Docker images automatically.
   Kubeconfig uses 127.0.0.1 - works directly.

2. DEVCONTAINER DEVELOPMENT (k3d or OrbStack-via-container)
   Developer runs `metta dev` inside a devcontainer.

   Option A: Use k3d (k3s-in-Docker) - creates K8s inside the container
   Option B: Connect to host's OrbStack from inside the container

   We chose Option B for Mac devcontainers because:
   - Reuses existing OrbStack setup (no duplicate K8s)
   - Docker socket is shared, so images built in container are visible
   - Simpler for developers already using OrbStack

   For Linux/remote devcontainers, we use k3d (Option A).

=============================================================================
KEY CHALLENGE: ORBSTACK FROM INSIDE A CONTAINER
=============================================================================

When running inside a container and connecting to host's OrbStack:

Problem 1: The kubeconfig uses 127.0.0.1, but from inside the container,
           127.0.0.1 refers to the container itself, not the host.
Solution:  Replace 127.0.0.1 with host.docker.internal (Docker's host DNS).

Problem 2: OrbStack's TLS certificate only includes these SANs:
           - localhost
           - 127.0.0.1
           - orbstack
           It does NOT include host.docker.internal.
Solution:  Use insecure-skip-tls-verify in the kubeconfig.
           This is acceptable for local dev - traffic is still TLS encrypted,
           we just skip hostname verification. The alternative would require
           modifying OrbStack's cert generation, which we can't do.

Problem 3: kubectl doesn't allow both certificate-authority-data AND
           insecure-skip-tls-verify in the same cluster config.
Solution:  We use regex to replace the CA data line entirely with the
           insecure-skip-tls-verify line.

See _get_orbstack_kubeconfig_for_container() for the implementation.
"""

import os
import platform
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from metta.common.util.fs import get_repo_root
from metta.setup.utils import error, info, success, warning

repo_root = get_repo_root()

NAMESPACE = "jobs"
IMAGE = "episode-runner-local:latest"


def _is_running_in_container() -> bool:
    """Detect if we're running inside a container (Docker, devcontainer, etc).

    This detection is crucial for deciding whether to modify kubeconfig for
    container-to-host communication. We use multiple heuristics because
    different container runtimes leave different markers:

    1. /.dockerenv file - Created by Docker
    2. REMOTE_CONTAINERS/CODESPACES env vars - Set by VS Code devcontainers
    3. /proc/1/cgroup contents - Shows "docker" or "kubepods" in containers

    Returns:
        True if running inside a container, False otherwise.
    """
    # Check for /.dockerenv file (Docker)
    if Path("/.dockerenv").exists():
        return True
    # Check for container environment variable (common in devcontainers)
    if os.environ.get("REMOTE_CONTAINERS") or os.environ.get("CODESPACES"):
        return True
    # Check cgroup for container indicators
    try:
        with open("/proc/1/cgroup", "r") as f:
            return "docker" in f.read() or "kubepods" in f.read()
    except (FileNotFoundError, PermissionError):
        pass
    return False


def _get_orbstack_kubeconfig_for_container() -> str | None:
    """Create a modified kubeconfig for accessing OrbStack from inside a container.

    This solves the "container-to-host K8s" problem described in the module docstring.

    The modification process:
    1. Read the host's kubeconfig (mounted via devcontainer.json)
    2. Parse it as YAML and find the OrbStack cluster entry
    3. Modify ONLY the OrbStack cluster's server URL (127.0.0.1 -> orbstack)
    4. Keep the certificate-authority-data (proper TLS verification)
    5. Write to ~/.kube/config-container (persistent across commands)

    IMPORTANT: We only modify the OrbStack cluster, not other clusters that might
    also use 127.0.0.1 (e.g., for kubectl proxy to production). This prevents
    accidentally routing non-local traffic through the wrong path.

    How TLS verification works:
    - OrbStack's K8s API server cert has SANs including "orbstack"
    - The devcontainer has --add-host=orbstack:host-gateway which makes
      "orbstack" resolve to the host's IP from inside the container
    - This allows proper TLS verification without insecure-skip-tls-verify

    Returns:
        Path to modified kubeconfig, or None if:
        - Not running in a container
        - Kubeconfig doesn't exist
        - Kubeconfig doesn't have an OrbStack cluster
    """
    import yaml  # noqa: PLC0415

    if not _is_running_in_container():
        return None

    # Read the current kubeconfig (mounted from host via devcontainer.json)
    kubeconfig_path = Path.home() / ".kube" / "config"
    if not kubeconfig_path.exists():
        return None

    try:
        content = kubeconfig_path.read_text()
        config = yaml.safe_load(content)
    except (PermissionError, OSError, yaml.YAMLError):
        return None

    if not config or "clusters" not in config:
        return None

    # Find and modify only the OrbStack cluster
    # OrbStack creates a cluster named "orbstack" with server at 127.0.0.1
    modified = False
    for cluster in config.get("clusters", []):
        cluster_name = cluster.get("name", "").lower()
        cluster_data = cluster.get("cluster", {})
        server = cluster_data.get("server", "")

        # Only modify clusters that are clearly OrbStack
        if "orbstack" in cluster_name and "127.0.0.1" in server:
            # Replace 127.0.0.1 with "orbstack" hostname
            # The devcontainer has --add-host=orbstack:host-gateway which makes
            # this hostname resolve to the host IP
            cluster_data["server"] = server.replace("127.0.0.1", "orbstack")
            modified = True

    if not modified:
        return None

    # Write to a persistent location so it survives across commands
    # Using config-container to avoid overwriting the original
    modified_config_path = Path.home() / ".kube" / "config-container"
    with open(modified_config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    return str(modified_config_path)


class K8sRuntime(Enum):
    """Supported local Kubernetes runtimes.

    ORBSTACK: macOS-only, provided by OrbStack (https://orbstack.dev)
              - Shares Docker images automatically (no import needed)
              - Uses context "orbstack"
              - Preferred for direct Mac development

    K3D: Cross-platform, runs k3s in Docker (https://k3d.io)
         - Requires explicit image import into cluster
         - Uses context "k3d-metta-local"
         - Used for devcontainers and Linux environments
    """

    ORBSTACK = "orbstack"
    K3D = "k3d"


# k3d cluster name used for observatory
K3D_CLUSTER_NAME = "metta-local"
K3D_CONTEXT = f"k3d-{K3D_CLUSTER_NAME}"
ORBSTACK_CONTEXT = "orbstack"


def detect_k8s_runtime() -> K8sRuntime | None:
    """Detect which K8s runtime is available and should be used.

    Detection order (first match wins):
    1. METTA_K8S_RUNTIME env var (explicit override)
    2. OrbStack context in kubeconfig (preferred on macOS)
    3. k3d context in kubeconfig (existing cluster)
    4. k3d binary available (can create cluster)
    5. orbctl binary available (OrbStack installed but K8s not enabled)

    When running in a container, we first check for a modified kubeconfig
    that can access the host's OrbStack. This allows Mac devcontainer users
    to reuse their existing OrbStack setup.

    Returns:
        K8sRuntime enum value, or None if no runtime is available.
    """
    # Check for explicit override via environment variable
    env_runtime = os.environ.get("METTA_K8S_RUNTIME", "").lower()
    if env_runtime == "orbstack":
        return K8sRuntime.ORBSTACK
    elif env_runtime == "k3d":
        return K8sRuntime.K3D

    # Prepare env with potentially modified kubeconfig for container access.
    # This is critical: we must use the modified kubeconfig when checking
    # for contexts, otherwise we won't detect OrbStack from inside a container.
    env = os.environ.copy()
    modified_config = _get_orbstack_kubeconfig_for_container()
    if modified_config:
        env["KUBECONFIG"] = modified_config

    # Auto-detect: check what's available
    result = subprocess.run(
        ["kubectl", "config", "get-contexts", "-o", "name"],
        capture_output=True,
        text=True,
        env=env,
    )
    contexts = result.stdout.split() if result.returncode == 0 else []

    # Prefer orbstack on macOS (it's simpler when available)
    if ORBSTACK_CONTEXT in contexts:
        return K8sRuntime.ORBSTACK

    # Check for existing k3d cluster
    if K3D_CONTEXT in contexts:
        return K8sRuntime.K3D

    # Check if k3d is installed (we can create a cluster)
    k3d_available = subprocess.run(["which", "k3d"], capture_output=True).returncode == 0
    if k3d_available:
        return K8sRuntime.K3D

    # Check if orbctl is installed (user might need to enable k8s)
    orbctl_available = subprocess.run(["which", "orbctl"], capture_output=True).returncode == 0
    if orbctl_available:
        return K8sRuntime.ORBSTACK

    return None


def get_k8s_context(runtime: K8sRuntime) -> str:
    """Get the kubectl context name for a runtime.

    Context names are fixed by the runtime:
    - OrbStack always uses "orbstack"
    - k3d uses "k3d-{cluster_name}" format
    """
    if runtime == K8sRuntime.ORBSTACK:
        return ORBSTACK_CONTEXT
    else:
        return K3D_CONTEXT


def get_host_address(runtime: K8sRuntime) -> str:
    """Get the hostname that pods use to reach the host machine.

    Different K8s runtimes provide different DNS names for pods to access
    services running on the host (like the Observatory backend server).

    This is used to configure the STATS_SERVER_URI that job pods use
    to report results back to the Observatory backend.

    Returns:
        "host.docker.internal" for OrbStack
        "host.k3d.internal" for k3d
    """
    if runtime == K8sRuntime.ORBSTACK:
        return "host.docker.internal"
    else:
        # k3d uses host.k3d.internal
        return "host.k3d.internal"


def _check_runtime(runtime: K8sRuntime) -> None:
    """Verify the K8s runtime is available and configured.

    Called before operations that require K8s. Provides helpful error
    messages if the runtime isn't ready.
    """
    context = get_k8s_context(runtime)
    env = _get_kubectl_env(runtime)
    result = subprocess.run(
        ["kubectl", "config", "get-contexts", "-o", "name"],
        capture_output=True,
        text=True,
        env=env,
    )
    contexts = result.stdout.split() if result.returncode == 0 else []

    if context not in contexts:
        if runtime == K8sRuntime.ORBSTACK:
            error("OrbStack Kubernetes is not available.")
            error("Please enable it: orb config set k8s.enable true")
            error("Then restart OrbStack.")
        else:
            error(f"k3d cluster '{K3D_CLUSTER_NAME}' is not running.")
            error("Create it with: metta dev local-k8s setup")
        sys.exit(1)


def _get_kubectl_env(runtime: K8sRuntime) -> dict[str, str]:
    """Get environment variables for kubectl commands.

    For OrbStack running from inside a container, this returns env with
    KUBECONFIG pointing to the modified config (host.docker.internal + skip TLS).

    This function is called by all kubectl wrappers to ensure consistent
    environment across all K8s operations.
    """
    env = os.environ.copy()

    # If using OrbStack from inside a container, use modified kubeconfig
    if runtime == K8sRuntime.ORBSTACK:
        modified_config = _get_orbstack_kubeconfig_for_container()
        if modified_config:
            env["KUBECONFIG"] = modified_config

    return env


def _kubectl(runtime: K8sRuntime, *args: str) -> subprocess.CompletedProcess[bytes]:
    context = get_k8s_context(runtime)
    env = _get_kubectl_env(runtime)
    return subprocess.run(["kubectl", "--context", context, *args], check=True, env=env)


def _ensure_k3d_cluster() -> None:
    """Create k3d cluster if it doesn't exist."""
    result = subprocess.run(
        ["k3d", "cluster", "list", "-o", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        import json  # noqa: PLC0415

        clusters = json.loads(result.stdout) if result.stdout.strip() else []
        if any(c.get("name") == K3D_CLUSTER_NAME for c in clusters):
            info(f"k3d cluster '{K3D_CLUSTER_NAME}' already exists")
            return

    info(f"Creating k3d cluster '{K3D_CLUSTER_NAME}'...")
    subprocess.run(
        [
            "k3d",
            "cluster",
            "create",
            K3D_CLUSTER_NAME,
            "--api-port",
            "6443",
            # Enable host.k3d.internal DNS for pod->host communication
            "--k3s-arg",
            "--disable=traefik@server:0",
        ],
        check=True,
    )
    success(f"k3d cluster '{K3D_CLUSTER_NAME}' created")


def _import_image_to_k3d() -> None:
    """Import the local Docker image into k3d cluster."""
    info(f"Importing {IMAGE} into k3d cluster...")
    subprocess.run(
        ["k3d", "image", "import", IMAGE, "-c", K3D_CLUSTER_NAME],
        check=True,
    )
    success("Image imported to k3d")


def _build_image() -> None:
    old_id = subprocess.run(["docker", "images", "-q", IMAGE], capture_output=True, text=True).stdout.strip()

    docker_platform = "linux/arm64" if platform.machine() in ("arm64", "aarch64") else "linux/amd64"
    info(f"Building {IMAGE} for {docker_platform}...")

    # Build context from working tree (includes uncommitted changes) using
    # git ls-files to respect .gitignore. Piped straight to docker build.
    dockerfile = Path(__file__).parent / "Dockerfile.episode_runner.local"
    dockerfile_rel = str(dockerfile.relative_to(repo_root))

    ls_files = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "packages/mettagrid",
            "packages/cogames",
        ],
        capture_output=True,
        check=True,
        cwd=repo_root,
    )
    # Append the Dockerfile to the file list (may not be git-tracked yet).
    tar_input = ls_files.stdout + dockerfile_rel.encode() + b"\0"

    tar = subprocess.Popen(
        ["tar", "-cf", "-", "-C", str(repo_root), "--null", "-T", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    tar_data, _ = tar.communicate(tar_input)
    if tar.returncode != 0:
        raise subprocess.CalledProcessError(tar.returncode, tar.args)

    subprocess.run(
        [
            "docker",
            "build",
            "-t",
            IMAGE,
            "-f",
            dockerfile_rel,
            "--platform",
            docker_platform,
            "-",
        ],
        input=tar_data,
        check=True,
    )

    if old_id:
        new_id = subprocess.run(["docker", "images", "-q", IMAGE], capture_output=True, text=True).stdout.strip()
        if new_id != old_id:
            info(f"Removing old image {old_id[:12]}...")
            subprocess.run(["docker", "rmi", old_id], capture_output=True)


local_k8s_app = typer.Typer(
    help="Manage local Kubernetes (OrbStack or k3d)", rich_markup_mode="rich", no_args_is_help=True
)


@local_k8s_app.command(name="setup")
def cmd_setup():
    """Build image and create jobs namespace."""
    runtime = detect_k8s_runtime()
    if runtime is None:
        error("No supported Kubernetes runtime found.")
        error("Install k3d (for containers/remote) or OrbStack (for macOS).")
        raise typer.Exit(1)

    info(f"Using K8s runtime: {runtime.value}")

    # For k3d, ensure cluster exists first
    if runtime == K8sRuntime.K3D:
        _ensure_k3d_cluster()

    _check_runtime(runtime)

    _build_image()

    # For k3d, we need to import the image into the cluster
    # OrbStack shares Docker images automatically
    if runtime == K8sRuntime.K3D:
        _import_image_to_k3d()
    else:
        success("Image built (OrbStack shares Docker images with k8s automatically)")

    context = get_k8s_context(runtime)
    env = _get_kubectl_env(runtime)
    result = subprocess.run(
        ["kubectl", "--context", context, "create", "namespace", NAMESPACE],
        capture_output=True,
        env=env,
    )
    if result.returncode != 0 and b"already exists" not in result.stderr:
        error(f"Failed to create namespace {NAMESPACE}")
        raise typer.Exit(1)
    success(f"{NAMESPACE} namespace ready")


@local_k8s_app.command(name="clean")
def cmd_clean():
    """Delete jobs namespace (and optionally k3d cluster)."""
    runtime = detect_k8s_runtime()
    if runtime is None:
        warning("No K8s runtime detected, nothing to clean")
        return

    _kubectl(runtime, "delete", "namespace", NAMESPACE, "--ignore-not-found=true")
    success("Namespace deleted")

    if runtime == K8sRuntime.K3D:
        delete_cluster = typer.confirm(f"Also delete k3d cluster '{K3D_CLUSTER_NAME}'?", default=False)
        if delete_cluster:
            subprocess.run(["k3d", "cluster", "delete", K3D_CLUSTER_NAME], check=True)
            success("k3d cluster deleted")


@local_k8s_app.command(name="get-pods")
def cmd_get_pods():
    """List job pods."""
    runtime = detect_k8s_runtime()
    if runtime is None:
        error("No K8s runtime detected")
        raise typer.Exit(1)
    _kubectl(runtime, "get", "pods", "-n", NAMESPACE)


@local_k8s_app.command(name="logs")
def cmd_logs(pod_name: Annotated[str | None, typer.Argument(help="Pod name")] = None):
    """Follow logs for job pods."""
    runtime = detect_k8s_runtime()
    if runtime is None:
        error("No K8s runtime detected")
        raise typer.Exit(1)

    if pod_name:
        _kubectl(runtime, "logs", pod_name, "-n", NAMESPACE, "--follow")
    else:
        _kubectl(runtime, "logs", "-n", NAMESPACE, "-l", "app=episode-runner", "--follow")


@local_k8s_app.command(name="build-image")
def cmd_build_image():
    """Rebuild the job runner Docker image."""
    runtime = detect_k8s_runtime()

    _build_image()

    # For k3d, re-import the image
    if runtime == K8sRuntime.K3D:
        _import_image_to_k3d()

    success("Image built")


@local_k8s_app.command(name="status")
def cmd_status():
    """Show current K8s runtime status."""
    runtime = detect_k8s_runtime()
    if runtime is None:
        error("No K8s runtime detected")
        info("Available options:")
        info("  - OrbStack (macOS): Install OrbStack and enable K8s")
        info("  - k3d (any platform): Install k3d and Docker")
        raise typer.Exit(1)

    context = get_k8s_context(runtime)
    host_addr = get_host_address(runtime)

    success(f"Runtime: {runtime.value}")
    info(f"Context: {context}")
    info(f"Host address (for pods): {host_addr}")

    # Check if cluster is actually reachable
    env = _get_kubectl_env(runtime)
    result = subprocess.run(
        ["kubectl", "--context", context, "cluster-info"],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode == 0:
        success("Cluster is reachable")
    else:
        warning("Cluster is not reachable")


def main():
    local_k8s_app()


if __name__ == "__main__":
    main()
