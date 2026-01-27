# Scripted Agent Registry

This snapshot mirrors the short-name registry in `cogames_agents.policy.scripted_registry`. Each entry maps to
`metta://policy/<short_name>`.

Regenerate the list with:

```bash
python -c "from cogames_agents.policy.scripted_registry import list_scripted_agent_names; print(list_scripted_agent_names())"
```

## Baselines and demos (Python)

- `baseline` - BaselinePolicy (exploration + gathering)
- `tiny_baseline` - DemoPolicy (minimal baseline)
- `ladybug_py` - UnclippingPolicy (handles clipped extractors)

## Nim multi-agent baselines

- `thinky` (`thinky_nim`) - Nim Thinky policy
- `race_car` (`race_car_nim`) - Nim RaceCar policy
- `ladybug` (`ladybug_nim`) - Nim Ladybug policy
- `nim_random` (`random_nim`) - Nim random policy

## CogsGuard (Nim)

- `role` (`role_nim`) - Nim multi-role policy
- `alignall` - Nim align-all policy

## CogsGuard (Python)

- `role_py` - Python multi-role policy
- `role_roster` (`role_mix`) - Roster/pattern-based initial vibe assignment
- `wombo` (`swiss`) - Generalist multi-role policy
- `wombo_mix` (`wombo10`) - Fixed role cycle by agent index
- `cogsguard_control` - Control variant
- `cogsguard_targeted` - Targeted variant
- `cogsguard_v2` - V2 variant
- `miner`, `scout`, `aligner`, `scrambler` - Role-specific policies
- `teacher` (`teacher_nim`) - Teacher wrapper over Nim multi-role

## Pinky (Python, CogsGuard)

- `pinky` - Role-count based policy (`?miner=...&scout=...&aligner=...&scrambler=...`)
