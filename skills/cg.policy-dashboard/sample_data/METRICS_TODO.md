# Dashboard Metrics Coverage Checklist

Track which metrics from cogames/mettagrid are demonstrated in the sample data.

**Last updated**: After comprehensive metric expansion

## Agent-Level Metrics (stats.agent)

### Action Metrics

- [x] `action.move.success` - Movement successes
- [x] `action.move.failed` - Movement failures
- [x] `action.noop.success` - No-op actions
- [x] `action.change_vibe.success` - Vibe change successes
- [x] `action.attack.success` - Attack successes
- [x] `action.attack.failed` - Attack failures
- [x] `action.failed` - Total failed actions
- [x] `action.timeout` - Action timeouts
- [x] `action.rotate.success` - Rotation successes
- [x] `action.rotate.failed` - Rotation failures
- [x] `action.pickup.success` - Pickup successes
- [x] `action.pickup.failed` - Pickup failures
- [x] `action.drop.success` - Drop successes
- [x] `action.drop.failed` - Drop failures
- [x] `action.put_recipe.success` - Recipe placement successes
- [x] `action.put_recipe.failed` - Recipe placement failures
- [x] `action.get_output.success` - Output retrieval successes
- [x] `action.get_output.failed` - Output retrieval failures
- [x] `actions.swap` - Swaps with frozen agents

### Attack Detail Metrics (per attacker/defender group)

- [x] `action.attack.{group}.blocked_by.{target_group}` - Attacks blocked
- [x] `action.attack.{group}.friendly_fire` - Friendly fire incidents
- [x] `action.attack.{group}.hit.{target_group}` - Attacks landed
- [x] `action.attack.{target_group}.hit_by.{actor_group}` - Attacks received

### Resource Metrics

- [x] `energy.amount` - Current energy
- [x] `energy.gained` - Energy gained
- [x] `energy.lost` - Energy lost
- [x] `carbon.amount` - Current carbon
- [x] `carbon.gained` - Carbon gained
- [x] `carbon.lost` - Carbon lost
- [x] `heart.amount` - Current hearts
- [x] `heart.gained` - Hearts gained
- [x] `heart.lost` - Hearts lost
- [x] `oxygen.amount` - Current oxygen
- [x] `oxygen.gained` - Oxygen gained
- [x] `oxygen.lost` - Oxygen lost
- [x] `silicon.amount` - Current silicon
- [x] `silicon.gained` - Silicon gained
- [x] `silicon.lost` - Silicon lost
- [x] `germanium.amount` - Current germanium
- [x] `germanium.gained` - Germanium gained
- [x] `germanium.lost` - Germanium lost
- [x] `aligner.amount` - Current aligners held
- [x] `aligner.gained` - Aligners picked up
- [x] `aligner.lost` - Aligners dropped/used

### Alignment Metrics (Agent)

- [x] `junction.aligned_by_agent` - Junctions aligned by agent
- [x] `junction.scrambled_by_agent` - Junctions scrambled
- [x] `aligner.aligned_by_agent` - Aligners aligned
- [x] `aligner.scrambled_by_agent` - Aligners scrambled

### Status Metrics

- [x] `status.frozen.ticks` - Total frozen time
- [x] `status.frozen.ticks.{group}` - Frozen time by attacker group
- [x] `status.max_steps_without_motion` - Max idle steps

---

## Game-Level Metrics (stats.game)

### Production Metrics

- [x] `assembler.heart.created` - Hearts created by assemblers
- [x] `chest.heart.deposited_by_agent` - Hearts deposited to chests
- [x] `chest.heart.withdrawn_by_agent` - Hearts withdrawn from chests
- [x] `converter.carbon.converted` - Carbon converted
- [x] `converter.silicon.converted` - Silicon converted
- [x] `mine.carbon.mined` - Carbon mined
- [x] `mine.silicon.mined` - Silicon mined
- [x] `generator.energy.generated` - Energy generated

### Object Count Metrics

- [x] `objects.wall` - Wall count
- [x] `objects.agent` - Agent count
- [x] `objects.junction` - Junction count
- [x] `objects.assembler` - Assembler count
- [x] `objects.chest` - Chest count
- [x] `objects.converter` - Converter count
- [x] `objects.mine` - Mine count
- [x] `objects.generator` - Generator count

### Observation Metrics

- [x] `tokens_written` - Observation tokens written
- [x] `tokens_dropped` - Observation tokens dropped
- [x] `tokens_free_space` - Observation buffer space

---

## Collective-Level Metrics (stats.collective)

### Alignment Tracking

- [x] `aligned.junction` - Currently aligned junctions
- [x] `aligned.junction.gained` - New junction alignments
- [x] `aligned.junction.lost` - Lost junction alignments
- [x] `aligned.junction.held` - Cumulative aligned junction-ticks
- [x] `aligned.aligner` - Currently aligned aligners
- [x] `aligned.aligner.gained` - New aligner alignments
- [x] `aligned.aligner.lost` - Lost aligner alignments
- [x] `aligned.aligner.held` - Cumulative aligned aligner-ticks

### Resource Deposits/Withdrawals

- [x] `heart.amount` - Collective heart inventory
- [x] `heart.deposited` - Hearts deposited to collective
- [x] `heart.withdrawn` - Hearts withdrawn from collective
- [x] `carbon.deposited` - Carbon deposited
- [x] `carbon.withdrawn` - Carbon withdrawn
- [x] `oxygen.deposited` - Oxygen deposited
- [x] `oxygen.withdrawn` - Oxygen withdrawn
- [x] `silicon.deposited` - Silicon deposited
- [x] `silicon.withdrawn` - Silicon withdrawn
- [x] `germanium.deposited` - Germanium deposited
- [x] `germanium.withdrawn` - Germanium withdrawn
- [x] `energy.deposited` - Energy deposited
- [x] `energy.withdrawn` - Energy withdrawn

---

## Coverage Summary

| Category           | Used | Available | Coverage |
| ------------------ | ---- | --------- | -------- |
| Action Metrics     | 19   | 19        | **100%** |
| Attack Details     | 4    | 4         | **100%** |
| Resource Metrics   | 21   | 21        | **100%** |
| Alignment (Agent)  | 4    | 4         | **100%** |
| Status Metrics     | 3    | 3         | **100%** |
| Game Metrics       | 11   | 11        | **100%** |
| Collective Metrics | 21   | 21        | **100%** |

**Overall: 100% of known metrics demonstrated**

---

## Episodes with Full Metric Coverage

The following episodes contain the complete metric set:

- `01_dominant_win.json` - High-performance baseline with all metrics
- `03_crushing_defeat.json` - Low-performance contrast with all metrics

Other episodes retain original metrics for variety and specific scenarios.

---

## Source Files

Key metric definitions found in:

- `packages/mettagrid/cpp/include/mettagrid/systems/stats_tracker.hpp`
- `packages/mettagrid/cpp/src/mettagrid/objects/agent.cpp`
- `packages/mettagrid/cpp/include/mettagrid/objects/collective.hpp`
- `packages/mettagrid/cpp/include/mettagrid/actions/action_handler.hpp`
- `packages/mettagrid/cpp/include/mettagrid/actions/attack.hpp`
- `packages/mettagrid/cpp/include/mettagrid/handler/mutations/alignment_mutation.hpp`
