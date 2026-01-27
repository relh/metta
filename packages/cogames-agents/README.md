# cogames-agents

Optional scripted policies for CoGames. Use them for quick baselines, play/eval smoke tests, or as teacher policies.

## Scripted policy registry

The registry at `cogames_agents.policy.scripted_registry` maps policy `short_names` to `metta://policy/...` URIs.
Scripted agents and teachers share these identifiers, so the same name works for evaluation, play, and
`TeacherConfig.policy_uri`.

To list the current names:

```
python -c "from cogames_agents.policy.scripted_registry import list_scripted_agent_names; print(list_scripted_agent_names())"
```

Common scripted policy names include:

- Baselines: `baseline`, `tiny_baseline`, `ladybug_py`
- CogsGuard core: `role` (`role_nim`), `role_py`, `wombo` (`swiss`)
- Teaching/roles: `teacher` (`teacher_nim`), `miner`, `scout`, `aligner`, `scrambler`
- Pinky: `pinky`

For the full registry snapshot (including aliases), see `docs/scripted-agent-registry.md`.

Role-specific policies are exposed via role names (miner/scout/aligner/scrambler). For the teacher policy, you can pass
`role_vibes` as a comma-separated list:

```
metta://policy/teacher?role_vibes=miner,scout
```

Roster/mix policies:

- `role_roster` (`role_mix`) supports `roster=` or `pattern=` to assign initial vibes.
- `wombo_mix` (`wombo10`) assigns a fixed role cycle (`aligner,miner,scrambler,scout`) by agent index.

Examples:

```
metta://policy/role_roster?roster=aligner,miner,scrambler,scout
metta://policy/role_roster?pattern=aligner,miner,scrambler,scout
metta://policy/wombo_mix
```

Pinky role counts are applied in a different order than CogsGuard:

- Pinky order: miner -> scout -> aligner -> scrambler, and any remaining agents stay default/noop.
- CogsGuard order: scrambler -> aligner -> miner -> scout, then fills remaining agents with gear.

Examples:

```
metta://policy/pinky?miner=4&aligner=2&scrambler=4
metta://policy/pinky?miner=2&scout=2&aligner=1&scrambler=1&debug=1
```

## Recipe usage

The `recipes.experiment.scripted_agents` recipe accepts the same scripted policy names:

```
./tools/run.py recipes.experiment.scripted_agents.play agent=thinky suite=cvc_arena
./tools/run.py recipes.experiment.scripted_agents.play agent=miner suite=cogsguard
```

## Included policies

- Short names map to the fastest implementation (Nim when available, otherwise Python).
- `_nim` aliases exist when there is a Nim implementation alongside Python.
- Teacher wrapper: `teacher` (`teacher_nim`) forces an initial role/vibe, then delegates to the Nim policy.
