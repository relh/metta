# cogames-agents

Optional scripted policies for CoGames. Use them for quick baselines, play/eval smoke tests, or as teacher policies.

## Scripted policy registry

The registry at `cogames_agents.policy.scripted_registry` maps short names to `metta://policy/...` URIs. The same
identifier works for evaluation, play, and `TeacherConfig.policy_uri`.

Available scripted policy names:

- `baseline`
- `starter` (core `cogames` policy; still usable via the registry)
- `tiny_baseline`
- `ladybug`
- `thinky`
- `race_car`
- `nim_ladybug`
- `nim_random`
- `nim_cogsguard`
- `cogsguard`
- `teacher`
- `miner`
- `scout`
- `aligner`
- `scrambler`

Role-specific policies are exposed via role names (miner/scout/aligner/scrambler). For the teacher policy, pass
`role_vibes` as a comma-separated list:

```
metta://policy/teacher?role_vibes=miner,scout
```

## Recipe usage

The `recipes.experiment.scripted_agents` recipe accepts the same scripted policy names:

```
./tools/run.py recipes.experiment.scripted_agents.play agent=thinky suite=cvc_arena
./tools/run.py recipes.experiment.scripted_agents.play agent=miner suite=cogsguard
```

## Included policies

- Nim policies (short names): `thinky`, `nim_random`, `race_car`, `nim_ladybug`, `nim_cogsguard`
- Python scripted policies: `baseline`, `tiny_baseline`, `ladybug`
- Core scripted policy (in `cogames`): `starter`
- Scripted roles: `miner`, `scout`, `aligner`, `scrambler`
- Teacher wrapper: `teacher` (forces an initial role/vibe, then delegates to the Nim policy)
