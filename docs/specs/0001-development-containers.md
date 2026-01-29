# Development Containers

> **Status:** Draft **Author:** Martin Hess **Created:** 2026-01-12 **Updated:** N/A

## Summary

Speedup new developers by eliminating friction and failures when attempting to create a build and runtime environment
for metta, and to more closely replicate the linux x86 deployment environment using development containers.

## Problem

Setting up the metta development environment is fragile and platform-dependent. Developers on ARM Macs face a different
runtime than the Linux x86 production environment, leading to "works on my machine" issues. The setup process has
multiple failure modes that can leave developers stuck with a broken environment.

- **Fragile setup process**: A misstep during configuration can leave developers with an inoperable environment that's
  difficult to diagnose and fix
- **Platform mismatch**: ARM Mac development differs from Linux x86 production, causing behavior discrepancies that only
  surface in CI/CD or production
- **Dependency conflicts**: Native dependencies (nim, bazel, system libraries) can conflict with existing system
  installations or require specific versions
- **Onboarding friction**: New developers spend significant time troubleshooting environment setup instead of
  contributing code
- **Inconsistent environments**: Each developer's machine accumulates unique state over time, making bugs harder to
  reproduce

### Goals

#### 1. At a top level:

- [ ] **One-click onboarding**: New developers can start contributing within minutes using a pre-configured container
- [ ] **Reproducible debugging**: "Works in the devcontainer" becomes a reliable baseline for reproducing issues
- [ ] **CI/CD parity**: Local development environment matches the build pipeline, catching issues before they hit CI
- [ ] **Remote dev containers**: enables remote container development when different hardware is necessary e.g. GPU
- [ ] **Make devcontainer for cogs**: maybe build and host the docker image as part of CD --- with uv, is this
      necessary?

#### 2. Enable appropriate metta commands:

#### Must haves

- [x] user config shell other tools shell customizations
- [x] install - Install or update components logs into services add llm login?
- [x] pytest - Python test runner CI calls
- [ ] observatory - Observatory local development run tournament locally will need port forwarding
- [x] cpptest - MettaGrid C++ test runner CI calls
- [x] nimtest - MettaGrid Nim test runner CI calls
- [ ] codebase - Codebase management tools generate protobuf generate mermaid
- [x] lint - Code formatters CI calls
- [ ] ci - Run CI checks locally stages - get in merge queue CI - push to main (not part of ci) CD -- build containers,
      restart kub (web site, tourney) Training
- [ ] run - Run component-specific commands used by git hooks and filter repo support git hooks
- [ ] configure - Configure Metta settings githooks
- [ ] metta help - change

#### Lower priority

- [ ] clean - Clean build artifacts and temporary files likely keep
- [ ] publish - Create and push a release tag for a package just sets a github tag, which triggers stuff
- [ ] gridworks - Start the Gridworks web UI slava uses?
- [ ] run-monitor - Monitor training runs used

#### Investigate deprecation

- [ ] status - Show status of components just have install?
- [ ] pr-feed - Show PRs that touch a specific path not used?
- [ ] build-dockerfiles - Build all repository Dockerfiles not used?

#### Deprecate

- [ ] tool - Run a tool from the tools/ directory toss
- [ ] shell - Start an IPython shell with Metta imports toss
- [ ] go - Navigate to a Softmax Home shortcut toss
- [ ] report-env-details - Report environment details including UV project directory not used
- [ ] clip - Copy codebase to clipboard. Pass through any codeclip flags not used
- [ ] book - Interactive marimo notebook commands toss

#### 3. Preserve what works

- [ ] Existing dev setup tools aren't impacted.

## Non-Goals

What is explicitly out of scope:

- devcontainer for other non-metta projects
- keeping non container dev setup tools at parity when/if devcontainer evolves

## Design

### Phase 1: prototype

- make dev container work
- make metta command work, but not sub commands

### Phase 2: the rest of it

- make each metta sub command work starting with the most used

## Open Questions

1. Not everything specified is important for developers, so need to prioritize, and prune
2. Some of these are already working, need to test
3. Some can be made to work easily, and others are more challenging
4. Some will require multiple containers, and there is some question on best way to approach
5. We want to make devcontainers part of the CI/CD verification process so that we know that devcontainers stay
   functioning - unclear what the minimal test to verify so that we aren't greatly increasing the checks time
6. We want to avoid having to log into various external services (Claude, etc.) when you start a container, so we should
   probably map relevant local files into the container

## References

- [devcontainers](https://containers.dev)
- [devpod](https://devpod.sh)
