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
- Nim baselines: `thinky`, `race_car`, `ladybug`, `nim_random`
- CogsGuard core: `role`, `role_py`, `wombo`
- CogsGuard variants: `alignall`, `cogsguard_control`, `cogsguard_targeted`, `cogsguard_v2`
- CogsGuard roles: `miner`, `scout`, `aligner`, `scrambler`
- Teacher: `teacher`
- Pinky: `pinky`

For the full registry snapshot, see `docs/scripted-agent-registry.md`.

Role-specific policies are exposed via role names (miner/scout/aligner/scrambler). For the teacher policy, you can pass
`role_vibes` as a comma-separated list:

```
metta://policy/teacher?role_vibes=miner,scout
```

Fixed-role mixes and explicit orderings are configured via `role_py` parameters:

Examples:

```
metta://policy/role_py?role_cycle=aligner,miner,scrambler,scout
metta://policy/role_py?role_order=aligner,miner,aligner,miner,scout
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
- See `docs/scripted-agent-registry.md` for the canonical short-name list.
- Teacher wrapper: `teacher` (`teacher_nim`) forces an initial role/vibe, then delegates to the Nim policy.

## Docs

- `docs/mettaboxes.md` (mettabox usage guide)
- `docs/aws-sso-on-mettabox.md` (AWS SSO login from inside mettabox containers)
