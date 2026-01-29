# Observatory Devcontainer Design Notes

This document explains the goals, design options we considered, and why we chose the final approach.

## Goals

### Primary Goal

Enable `metta observatory` to work inside a devcontainer with the same developer experience as running directly on
macOS.

### Requirements

1. **Zero additional setup** - Developers shouldn't need to configure anything beyond opening the devcontainer
2. **Identical commands** - `metta observatory up` should work the same way in both environments
3. **Preserve Mac workflow** - Existing developers using OrbStack directly on Mac should see no changes
4. **Browser access** - Web UI must be accessible from the host browser
5. **Full functionality** - All services (postgres, server, frontend, watcher, tournament, job pods) must work

### Non-Goals

- Supporting Windows (not in our developer base)
- Running production workloads in containers
- Replacing OrbStack for direct Mac development

## The Core Challenge

Observatory requires Kubernetes to run job pods. On macOS, we use OrbStack which provides a lightweight K8s cluster. The
challenge is: how do we provide K8s when running inside a devcontainer?

## Design Options Considered

### Option 1: k3d Inside the Devcontainer

**Approach:** Install k3d in the devcontainer and create a k3s cluster inside Docker-in-Docker.

```
┌─────────────────────────────────────────┐
│              HOST (macOS)               │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │          DEVCONTAINER             │  │
│  │                                   │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │    Docker-in-Docker         │  │  │
│  │  │                             │  │  │
│  │  │  ┌───────────────────────┐  │  │  │
│  │  │  │   k3s (Kubernetes)    │  │  │  │
│  │  │  │                       │  │  │  │
│  │  │  │  ┌─────────────────┐  │  │  │  │
│  │  │  │  │   Job Pods      │  │  │  │  │
│  │  │  │  └─────────────────┘  │  │  │  │
│  │  │  └───────────────────────┘  │  │  │
│  │  └─────────────────────────────┘  │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

**Pros:**

- Fully isolated - no dependency on host configuration
- Works on any host OS (Linux, Mac, Windows)
- Consistent environment across all developers

**Cons:**

- Performance overhead of nested virtualization
- Must rebuild/import Docker images into k3d cluster
- More complex networking (multiple layers of NAT)
- Longer startup time
- Higher memory usage
- Diverges from Mac developer workflow (they use OrbStack)

### Option 2: Connect to Host's OrbStack

**Approach:** Mount the host's kubeconfig and Docker socket, connect to OrbStack running on the host.

```
┌─────────────────────────────────────────┐
│              HOST (macOS)               │
│                                         │
│  ┌─────────────┐    ┌─────────────────┐ │
│  │  OrbStack   │    │  Docker Daemon  │ │
│  │  (K8s)      │    │                 │ │
│  │             │    │  ┌───────────┐  │ │
│  │ ┌─────────┐ │    │  │ Postgres  │  │ │
│  │ │Job Pods │ │    │  └───────────┘  │ │
│  │ └─────────┘ │    │                 │ │
│  └──────┬──────┘    └────────┬────────┘ │
│         │                    │          │
│  ───────┼────────────────────┼───────── │
│         │ ~/.kube            │ socket   │
│  ┌──────┴────────────────────┴────────┐ │
│  │          DEVCONTAINER              │ │
│  │                                    │ │
│  │  metta observatory up              │ │
│  │  (connects to host services)       │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

**Pros:**

- No performance overhead - uses existing OrbStack
- Docker images built in container are immediately available to K8s
- Simpler architecture - fewer moving parts
- Same K8s environment as direct Mac development
- Fast startup - no cluster creation needed
- Lower memory usage

**Cons:**

- Requires OrbStack on the host (Mac-only)
- More complex networking (must use host.docker.internal)
- TLS certificate workaround needed (insecure-skip-tls-verify)
- Tighter coupling between container and host

### Option 3: Remote Kubernetes Cluster

**Approach:** Connect to a shared remote K8s cluster for development.

**Pros:**

- Works from any environment
- Shared resources across team
- More realistic production-like environment

**Cons:**

- Requires infrastructure setup and maintenance
- Network latency for local development
- Cost of running remote cluster
- Complexity of managing shared state
- Not suitable for offline development

### Option 4: Mock Kubernetes

**Approach:** Create a mock K8s client that simulates pod lifecycle without real K8s.

**Pros:**

- No K8s dependency at all
- Fast and lightweight
- Works anywhere

**Cons:**

- Significant development effort
- May miss real K8s behaviors
- Different code path than production
- Doesn't test actual job execution

## Decision: Option 2 (Connect to Host's OrbStack)

We chose Option 2 for Mac devcontainers, with Option 1 (k3d) as a fallback for Linux environments.

### Rationale

1. **Developer workflow preservation** Our developers already use OrbStack on Mac. Option 2 means they can switch
   between direct Mac development and devcontainer development seamlessly - same K8s cluster, same Docker images, same
   commands.

2. **Performance** k3d-in-Docker adds measurable overhead. For a development tool used daily, performance matters.

3. **Simplicity for the common case** Most of our developers are on Mac with OrbStack. Optimizing for this case while
   supporting alternatives is better than a one-size-fits-all approach that's suboptimal for everyone.

4. **Image sharing** With Option 2, when you build a Docker image in the devcontainer, it's immediately available to
   OrbStack's K8s. With Option 1, you'd need to import images into the k3d cluster.

5. **Resource usage** Running k3s inside Docker inside the devcontainer uses significantly more memory than connecting
   to existing OrbStack.

### Addressing the Cons

**"Requires OrbStack on the host"** - This is already our standard. All Mac developers have OrbStack installed.

**"Complex networking"** - We solve this once in `local_k8s.py`. Developers don't see the complexity.

**"TLS certificate workaround"** - The `insecure-skip-tls-verify` is for local development only. Traffic is still
encrypted, we just skip hostname verification. This is acceptable for a dev environment.

**"Tighter coupling"** - True, but the coupling is to a well-defined interface (K8s API, Docker socket). The code
cleanly abstracts this in `local_k8s.py`.

## Hybrid Approach: Runtime Detection

To support both Mac (OrbStack) and Linux (k3d) developers, we implemented runtime detection:

```python
def detect_k8s_runtime() -> K8sRuntime | None:
    # 1. Check for explicit override
    if os.environ.get("METTA_K8S_RUNTIME"):
        return ...

    # 2. Check for OrbStack context (prefer on Mac)
    if "orbstack" in kubectl_contexts:
        return K8sRuntime.ORBSTACK

    # 3. Check for k3d context
    if "k3d-metta-local" in kubectl_contexts:
        return K8sRuntime.K3D

    # 4. Check what can be created
    if k3d_available:
        return K8sRuntime.K3D
    if orbctl_available:
        return K8sRuntime.ORBSTACK
```

This means:

- Mac devcontainer → automatically uses host's OrbStack
- Linux devcontainer → automatically uses k3d
- Explicit override → `METTA_K8S_RUNTIME=k3d` forces k3d anywhere

## Key Technical Decisions

### Decision: Modify kubeconfig at runtime vs. static config

**Options:**

1. Require developers to manually create a container-compatible kubeconfig
2. Generate modified kubeconfig at runtime

**Choice:** Runtime generation

**Why:** Zero developer setup. The container detection and kubeconfig modification happen transparently in
`_get_orbstack_kubeconfig_for_container()`.

### Decision: insecure-skip-tls-verify vs. custom CA

**Options:**

1. Skip TLS hostname verification
2. Generate custom CA and certificates that include host.docker.internal
3. Add host.docker.internal to OrbStack's certificate

**Choice:** Skip TLS verification

**Why:** Options 2 and 3 require modifying OrbStack's configuration or running our own certificate infrastructure. For
local development, skipping hostname verification is acceptable - the connection is still encrypted.

### Decision: Docker socket mount vs. Docker-in-Docker

**Options:**

1. Mount host's Docker socket (`/var/run/docker.sock`)
2. Run Docker daemon inside the container (DinD)

**Choice:** Socket mount

**Why:**

- Simpler - no Docker daemon to manage
- Postgres runs on host Docker where it's already configured
- Docker images built in container are visible to host's K8s
- Less resource usage

### Decision: Port forwarding via runArgs vs. forwardPorts

**Options:**

1. Use devcontainer.json `forwardPorts` (VS Code feature)
2. Use `runArgs` with `-p` flags (Docker feature)

**Choice:** Both, with `-p` flags doing the actual work

**Why:** `forwardPorts` only works in VS Code. The `-p` flags work universally (Cursor, CLI, etc.). We keep
`forwardPorts` for VS Code UI integration.

### Decision: Environment-based configuration vs. config files

**Options:**

1. Different config files for container vs. host
2. Environment variables set at runtime

**Choice:** Environment variables

**Why:**

- Single source of truth in code
- No config file duplication
- Easy to override for testing
- Detection logic is explicit and testable

## Future Considerations

### If we need to support Windows

Option 1 (k3d inside container) would work on Windows. The runtime detection already supports k3d, so this would mostly
work out of the box.

### If we need offline development

The current approach requires OrbStack running on host. For true offline, we could:

- Cache the kubeconfig modification
- Pre-pull required images
- Add offline detection to skip K8s-dependent features

### If we need to test against different K8s versions

k3d supports specifying K8s versions. We could add a flag:

```bash
METTA_K8S_VERSION=1.28 metta observatory up
```

### If OrbStack changes their certificate SANs

If OrbStack adds `host.docker.internal` to their K8s API server certificate, we could remove the
`insecure-skip-tls-verify` workaround. The code would automatically use the CA if the hostname matches.

## Summary

| Aspect              | Decision              | Rationale                                      |
| ------------------- | --------------------- | ---------------------------------------------- |
| Primary K8s source  | Host's OrbStack       | Performance, simplicity, workflow preservation |
| Fallback K8s        | k3d in container      | Linux support, explicit override               |
| Container detection | Multiple heuristics   | Reliability across container runtimes          |
| Kubeconfig handling | Runtime modification  | Zero developer setup                           |
| TLS verification    | Skip hostname check   | Acceptable for local dev                       |
| Docker access       | Socket mount          | Simpler, image sharing                         |
| Port forwarding     | runArgs -p flags      | Universal compatibility                        |
| Configuration       | Environment variables | Single source of truth                         |

The result is a system that "just works" for developers - they open the devcontainer and run `metta observatory up` with
no additional configuration.
