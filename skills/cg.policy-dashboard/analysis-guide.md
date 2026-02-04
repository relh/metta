# CoGames Tournament Analysis Guide

Reference guide for analyzing CoGames tournament policy performance. Used by analysis tools and dashboards.

## Metrics Reference

### Episode-Level Metrics

| Metric   | Description         | Typical Range | Notes                 |
| -------- | ------------------- | ------------- | --------------------- |
| `steps`  | Episode length      | 500-10000     | Max varies by mission |
| `reward` | Total policy reward | 0-60          | Sum across all agents |

### Agent Action Metrics

Aggregated across all agents controlled by your policy.

| Metric         | Description                          | Typical Range | Good Value        |
| -------------- | ------------------------------------ | ------------- | ----------------- |
| `move.success` | Successful movement actions          | 5000-9000     | >7000             |
| `move.failed`  | Failed movement attempts             | 1000-3000     | <2000             |
| `move.blocked` | Movement blocked by obstacles/agents | 500-2000      | <1500             |
| `noop`         | No-operation actions                 | 200-2000      | Context-dependent |

### Resource Metrics

| Metric                | Description                      | Typical Range | Notes |
| --------------------- | -------------------------------- | ------------- | ----- |
| `carbon.gathered`     | Carbon extracted from extractors | 0-500         |       |
| `carbon.deposited`    | Carbon deposited at hub          | 0-400         |       |
| `oxygen.gathered`     | Oxygen extracted                 | 0-500         |       |
| `oxygen.deposited`    | Oxygen deposited                 | 0-400         |       |
| `silicon.gathered`    | Silicon extracted                | 0-500         |       |
| `silicon.deposited`   | Silicon deposited                | 0-400         |       |
| `germanium.gathered`  | Germanium extracted              | 0-500         |       |
| `germanium.deposited` | Germanium deposited              | 0-400         |       |

### Gear Metrics

| Metric             | Description            | Notes                       |
| ------------------ | ---------------------- | --------------------------- |
| `miner.gained`     | Miner gear pickups     | Enables resource extraction |
| `miner.lost`       | Miner gear lost        | Death or dropped            |
| `aligner.gained`   | Aligner gear pickups   | Enables junction alignment  |
| `aligner.lost`     | Aligner gear lost      |                             |
| `scrambler.gained` | Scrambler gear pickups | Enables junction scrambling |
| `scrambler.lost`   | Scrambler gear lost    |                             |
| `scout.gained`     | Scout gear pickups     | Enables exploration bonuses |
| `scout.lost`       | Scout gear lost        |                             |
| `heart.gained`     | Hearts collected       | Required for align/scramble |
| `heart.lost`       | Hearts used/lost       |                             |

### Junction Metrics (Collective)

| Metric                  | Description                     | Notes                 |
| ----------------------- | ------------------------------- | --------------------- |
| `cogs.junction`         | Current cogs-aligned junctions  | End-of-episode count  |
| `cogs.junction.gained`  | Junctions aligned to cogs       | During episode        |
| `cogs.junction.lost`    | Cogs junctions lost             | Scrambled by opponent |
| `clips.junction`        | Current clips-aligned junctions |                       |
| `clips.junction.gained` | Junctions aligned to clips      |                       |
| `clips.junction.lost`   | Clips junctions lost            |                       |

### Influence Metrics

| Metric             | Description           | Typical Range |
| ------------------ | --------------------- | ------------- |
| `influence.gained` | Influence accumulated | 0-50000       |
| `influence.lost`   | Influence spent/lost  | 0-10000       |

### Combat/HP Metrics

| Metric      | Description     | Notes                      |
| ----------- | --------------- | -------------------------- |
| `hp.gained` | HP regenerated  | From healing stations      |
| `hp.lost`   | HP damage taken | From combat or environment |

---

## Key Performance Indicators

### Tier 1: Primary Score Drivers

These metrics have the strongest correlation with tournament score:

1. **Junction Control** - `cogs.junction.gained`, `clips.junction.gained`
   - Active junction manipulation is the biggest differentiator between top and bottom policies
   - Zero junction activity almost guarantees low scores

2. **Influence** - `influence.gained`
   - Proxy for overall game participation and territorial control
   - Top policies: 5000-15000 avg
   - Bottom policies: 0-1000 avg

3. **Reward Distribution**
   - Consistent non-zero rewards beats occasional high scores
   - Target: >80% of episodes with reward > 0.1

### Tier 2: Efficiency Metrics

4. **Resource Efficiency** - `{resource}.deposited` / steps
   - Good: >0.05 resources per step
   - Indicates agents are gathering and depositing, not stuck

5. **Hearts Usage** - `junction.gained` / `heart.lost`
   - Efficiency of converting hearts to junction control
   - Good: >0.5 junctions per heart

### Tier 3: Health Indicators

6. **Movement Success Rate** - `move.success` / (`move.success` + `move.failed`)
   - Good: >75%
   - Low rates indicate pathfinding issues or opponent blocking

7. **Noop Rate** - `noop` / total_actions
   - Good: <15%
   - High rates indicate policy indecision or stuck states

---

## Diagnostic Patterns

### High move_blocked + Low reward

**Diagnosis:** Pathfinding issue or opponent crash

- Check if opponent policy crashed mid-game (common with CCC policies)
- Crashed agents become immobile obstacles
- Look for: `move.blocked` > 5000, movement success < 30%

### Zero junction activity + Non-zero hearts

**Diagnosis:** Aligner/scrambler not activating

- Policy acquires hearts but doesn't use them
- Check gear acquisition: does policy get aligner/scrambler gear?
- May indicate goal-tree or decision logic bug

### High noop count

**Diagnosis:** Policy indecision or stuck state

- Noop > 2000 suggests policy frequently choosing to do nothing
- May indicate: unclear goals, navigation deadlock, or bug

### High rewards with one opponent, zero with another

**Diagnosis:** Opponent-specific interaction issue

- Some opponent behaviors may break your policy's assumptions
- Check if low-scoring opponent crashes or has unusual behavior

### Decreasing rewards over episode index

**Diagnosis:** Learning/adaptation problem or meta-game shift

- If recent episodes score worse, may indicate:
  - Opponents adapted to your strategy
  - Bug introduced in recent policy version
  - Seasonal meta-game change

### High HP lost + Low reward

**Diagnosis:** Losing combat encounters

- Policy may be engaging in fights it can't win
- Or: not retreating when low HP
- Check survival rate and retreat behavior

---

## Comparative Benchmarks

Based on top-10 leaderboard policies (as of current season):

| Metric             | Bottom 50% | Top 10%    | Elite (#1-3) |
| ------------------ | ---------- | ---------- | ------------ |
| Avg Reward         | 0-1.0      | 2.0-4.0    | 4.0+         |
| Junction Aligned   | 0-2        | 4-8        | 8+           |
| Influence Gained   | 0-2000     | 5000-15000 | 10000+       |
| Move Success Rate  | 60-75%     | 80-90%     | 85-95%       |
| Resource Total     | 50-150     | 200-400    | 300+         |
| Non-Zero Episode % | 10-40%     | 60-80%     | 90%+         |

---

## Analysis Workflows

### Debugging a Score Regression

When a new policy version scores worse than previous:

1. **Compare reward distributions**
   - Is it uniform decrease or specific failure mode?

2. **Check failure rate**
   - More crashes/timeouts/OOMs?

3. **Compare behavioral metrics**
   - Movement, junction, resource differences

4. **Identify changed matchups**
   - Did a specific opponent become problematic?

5. **Review low-scoring episodes**
   - What do the bottom 10% have in common?

### Understanding a Bad Matchup

When your policy consistently loses to a specific opponent:

1. **Segment episodes by this opponent**

2. **Compare metrics vs your overall average**
   - What's different against this opponent?

3. **Check team composition**
   - Do you lose more in 2v6 or 6v2?

4. **Watch replay of worst episode**
   - Visual inspection often reveals issue

5. **Check opponent behavior**
   - Do they use a strategy your policy doesn't handle?

### Identifying Behavioral Gaps

Finding what your policy doesn't do that top policies do:

1. **Benchmark against top policies**
   - Which metrics are you significantly below?

2. **Check role coverage**
   - Do you gather resources? Control junctions? Both?

3. **Analyze high-scoring vs low-scoring episodes**
   - What behaviors appear in high but not low?

4. **Look for zero-count metrics**
   - Any capability you never use? (e.g., scrambling)

---

## Team Composition Effects

### 6v2 (You have majority)

- More opportunities for role specialization
- Can dedicate agents to different tasks
- Typical advantage: +10-20% reward

### 2v6 (You have minority)

- Must be efficient with fewer agents
- Tests individual agent quality
- Good policies maintain similar performance

### 4v4 (Even)

- Direct competition
- No team size advantage
- Most balanced test of policy quality

**Red flag:** Large performance gap between 6v2 and 2v6 suggests over-reliance on agent count rather than smart
behavior.

---

## Error Types

### timeout

- Job exceeded time limit
- Cause: Policy inference too slow, or infinite loop
- Action: Profile policy, optimize inference

### oom

- Out of memory
- Cause: Policy uses too much RAM
- Action: Reduce model size, batch sizes, or memory leaks

### policy_error

- Policy raised an exception
- Cause: Bug in policy code
- Action: Check job logs for stack trace

### unknown

- Other failure
- Cause: Infrastructure issue, network, etc.
- Action: Check logs, may be transient
