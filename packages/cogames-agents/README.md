# cogames-agents

Optional scripted policies for CoGames. Use them for quick baselines, play/eval smoke tests, or as teacher policies.

## Scripted policy registry

The registry at `cogames_agents.policy.scripted_registry` maps short names to `metta://policy/...` URIs. Scripted agents
and teachers share these identifiers, so the same name works for evaluation, play, and `TeacherConfig.policy_uri`.

Available scripted policy names:

- `baseline`
- `ladybug`
- `thinky`
- `race_car`
- `nim_random`
- `cogsguard`
- `cogsguard_py`
- `teacher`
- `miner`
- `scout`
- `aligner`
- `scrambler`

Role-specific policies are exposed via role names (miner/scout/aligner/scrambler). For the teacher policy, you can pass
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

- Nim policies (short names; default when both exist): `thinky`, `nim_random`, `race_car`, `ladybug`, `cogsguard`
- Python scripted policies (use `_py` only when Nim exists): `baseline`, `tiny_baseline`, `ladybug_py`, `cogsguard_py`
- Core scripted policy (in `cogames`): `starter`
- Scripted roles: `miner`, `scout`, `aligner`, `scrambler`
- Teacher wrapper: `teacher` (forces an initial role/vibe, then delegates to the Nim policy)
