# Policy Process Isolation

> **Status:** Draft **Author:** Nishad **Created:** 2026-02-02

Implements the "multiple Python processes" phase from
[0015-thunderdome-policy-isolation](0015-thunderdome-policy-isolation.md).

## Summary

Run each policy in its own process, communicating with the game via HTTP using the existing Policy v1 protocol. The game
subprocess never imports policy code.

## Problem

Running all policies in the same process as the game engine causes:

- **Dependency conflicts**: policies may require different versions of the same library, or pollute global namespace
- **Stability risk**: a misbehaving policy can crash or hang the entire game process
- **Resource contention**: heavy policies (GPU inference) compete with the simulation
- **No isolation**: policies share memory space, which matters for tournament security

## Solution

The episode orchestrator spawns one HTTP policy server per unique policy, then launches the game subprocess with
lightweight client policies that forward `step()` calls over HTTP.

```
single_episode_runner.py (orchestrator)
  |
  |-- spawn --> policy server 0  (serve_policy.py, policy A, own process)
  |-- spawn --> policy server 1  (serve_policy.py, policy B, own process)
  |-- spawn --> game subprocess   (pure_single_episode_runner)
  |               |
  |               |-- RemoteMultiAgentPolicy(server 0)
  |               |     |-- RemoteAgentPolicy(agent 0) --HTTP--> server 0
  |               |     |-- RemoteAgentPolicy(agent 2) --HTTP--> server 0
  |               |-- RemoteMultiAgentPolicy(server 1)
  |               |     |-- RemoteAgentPolicy(agent 1) --HTTP--> server 1
  |               |-- Rollout (unchanged)
  |
  |-- wait for game subprocess to finish
  |-- kill policy servers
  |-- upload results
```

`Rollout` is unchanged. It still calls `agent_policy.step(obs)`. The `RemoteAgentPolicy` implementation serializes the
observation, makes an HTTP call, and returns the action.

The orchestrator always converts policy URIs to HTTP server URLs before passing them to the game subprocess, so the game
process never imports policy code (excluding the lightweight client stubs `RemoteMultiAgentPolicy` / `RemoteAgentPolicy`
which contain no policy logic).

## Goals

- Policy server launchable as a managed subprocess with port discovery
- `RemoteMultiAgentPolicy` in cogames implements `MultiAgentPolicy` over HTTP
- `single_episode_runner` spawns servers, passes HTTP URIs to game subprocess
- Game subprocess never imports policy code
- Existing episode runner tests pass (or are updated for new architecture)
- Integration test exercising the full stack end-to-end

## Non-Goals

- VM-level or container-level isolation (see [0015](0015-thunderdome-policy-isolation.md))
- Batched stepping (one HTTP call per agent per step for now)
- PolicyEnvInterface derived from PreparePolicy protobuf (see Future Work)

## Design

### Policy Server Subprocess Management

`serve_policy.py` already accepts `--port 0` for OS-assigned ports. A `--port-file` flag is added so the parent can
discover the bound port without parsing stdout. The parent polls for the file, then health-checks `GET /health`.

New `metta/sim/policy_server_manager.py`:

- `PolicyServerHandle`: dataclass with `port`, `process`, `shutdown()`
- `launch_policy_server(policy_uri, env_interface, *, startup_timeout)`:
  1. Write PolicyEnvInterface JSON to temp file
  2. Spawn `serve_policy.py` with `--port 0 --port-file <tmp>`
  3. Poll for port file, then `GET /health`
  4. Return handle

### Remote Policy Client

New `packages/cogames/src/metta_alo/policy/remote.py`:

`RemoteMultiAgentPolicy(base_url, env_interface)`:

- Implements `MultiAgentPolicy`
- Calls PreparePolicy eagerly in the constructor (sends game rules, agent IDs, TRIPLET_V1 format)
- Episode ID is provided by the caller or defaults to a client-side UUID

`RemoteAgentPolicy(parent, agent_id)`:

- Implements `AgentPolicy`
- `step(obs)`: serialize tokens to TRIPLET_V1 bytes via `raw_token`, POST BatchStep, map action_id back to name

Observation serialization uses the protobuf-defined TRIPLET_V1 format: raw bytes are base64-encoded and sent inside the
JSON envelope. The client constructs JSON matching the proto schema directly to avoid a proto build dependency in
cogames. Future work: use generated proto code if cogames gains proto support.

## Future Work

- **PolicyEnvInterface via protobuf**: type PolicyEnvInterface into the PreparePolicy request so the server derives it
  from the protocol message, not a CLI file path. This removes a class of mismatch bugs and lets the server be fully
  stateless with respect to environment configuration.
- **Batch stepping**: collect all agent observations per policy, one BatchStep call per step
