# Cogsguard sweep summary: relh.cogsguard.0129 (2026-01-29)

Summary of sweep `relh.cogsguard.0129` with patterns worth follow-up.

## Scope

- Sweep group: `relh.cogsguard.0129`
- Runs analyzed: 44
- Primary metric: `env_collective/cogs/aligned.junction.held`
- Sweep score: `sweep/score` (same metric as above)

## Top runs by aligned.junction.held

```
239.5             relh.cogsguard.0129_trial_0014_6a2d0b
161               relh.cogsguard.0129_trial_0040_83b563
159.66666666666666 relh.cogsguard.0129_trial_0026_148b1e
151.25            relh.cogsguard.0129_trial_0029_4406a5
106               relh.cogsguard.0129_trial_0012_a0611b
```

## Best run hyperparameters (trial_0014_6a2d0b)

Sweep suggestion values:

- `variants`: `["credit"]`
- `trainer.sampling.method`: `prioritized`
- `trainer.sampling.prio_alpha`: `0.3098`
- `trainer.sampling.prio_beta0`: `0.7994`
- `trainer.advantage.gae_lambda`: `0.9161`
- `trainer.advantage.gamma`: `0.9995`
- `trainer.losses.ppo_actor.clip_coef`: `0.3644`
- `trainer.losses.ppo_actor.ent_coef`: `0.0717`
- `trainer.losses.ppo_critic.vf_clip_coef`: `0.1`
- `trainer.losses.ppo_critic.vf_coef`: `1.3652`
- `trainer.optimizer.learning_rate`: `0.00924`
- `trainer.optimizer.momentum`: `0.9724`
- `trainer.optimizer.weight_decay`: `0.10`
- `trainer.optimizer.eps`: `2.50e-06`
- `trainer.optimizer.warmup_steps`: `1752`
- `policy_architecture.actor_hidden`: `384`
- `policy_architecture.critic_hidden`: `768`
- `policy_architecture.latent_dim`: `96`
- `policy_architecture.core_resnet_layers`: `1`
- `policy_architecture.core_num_heads`: `4`
- `policy_architecture.core_num_latents`: `16`

Diffs vs current defaults (`TrainerConfig()` + `ViTDefaultConfig(obs_shim_ignore_inventory_power_tokens=False)`):

- `variants`: default `None` -> `["credit"]`
- `trainer.sampling.method`: `sequential` -> `prioritized`
- `trainer.losses.ppo_actor.ent_coef`: `0.01` -> `0.0717`
- `trainer.losses.ppo_critic.vf_coef`: `0.4966` -> `1.3652`
- `trainer.losses.ppo_actor.clip_coef`: `0.2202` -> `0.3644`
- `trainer.optimizer.weight_decay`: `0.01` -> `0.10`
- `trainer.optimizer.learning_rate`: `0.00738` -> `0.00924`
- `trainer.optimizer.momentum`: `0.9` -> `0.9724`
- `trainer.optimizer.warmup_steps`: `1000` -> `1752`
- `trainer.optimizer.eps`: `5.08e-07` -> `2.50e-06`
- `trainer.advantage.gamma`: `1.0` -> `0.9995`
- `trainer.advantage.gae_lambda`: `0.95` -> `0.9161`
- `policy_architecture.actor_hidden`: `256` -> `384`
- `policy_architecture.critic_hidden`: `512` -> `768`
- `policy_architecture.latent_dim`: `128` -> `96`
- `policy_architecture.core_resnet_layers`: `2` -> `1`
- `policy_architecture.core_num_latents`: `12` -> `16`

## Patterns across the sweep (quick scan)

Pearson correlations (n=44) vs `sweep/score` for suggestion fields; weak-to-moderate but useful for follow-up.

Top absolute correlations:

- `trainer.losses.ppo_actor.ent_coef`: +0.27
- `trainer.optimizer.weight_decay`: +0.25
- `trainer.advantage.gamma`: +0.20
- `policy_architecture.core_resnet_layers`: -0.18
- `trainer.losses.ppo_critic.vf_clip_coef`: -0.15

Categorical comparisons (mean `sweep/score`):

- `trainer.sampling.method`:
  - `prioritized`: 39 runs, mean ~41.36
  - `sequential`: 5 runs, mean ~29.47
- `variants`:
  - `["milestones"]`: 10 runs, mean ~43.68
  - `["credit"]`: 34 runs, mean ~38.93

Notes:

- `milestones` averages higher, but with fewer runs.
- `prioritized` sampling outperforms `sequential` in this sweep.
- Higher entropy and weight decay correlate with better scores.
- Fewer `core_resnet_layers` are mildly favored.

## Suggested next steps

1. Replicate the best settings in a short controlled run (same seed) to confirm stability.
2. Run a focused mini-sweep with `prioritized` sampling, exploring:
   - `ent_coef` in the 0.05-0.10 range
   - `vf_coef` in the 1.0-1.5 range
   - `weight_decay` in the 0.05-0.15 range
3. Compare `variants=["credit"]` vs `variants=["milestones"]` with the same optimizer + architecture.
4. If training is stable, increase `actor_hidden`/`critic_hidden` while keeping `latent_dim=96` and
   `core_resnet_layers=1` to see if larger heads improve `aligned.junction.held`.
