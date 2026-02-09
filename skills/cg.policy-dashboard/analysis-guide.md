# CoGames Tournament Analysis Guide

Reference guide for analyzing CoGames tournament policy performance. Used by analysis tools and dashboards.

## Filter Types

There are exactly two kinds of filters. Getting them wrong changes what the dashboard computes.

### Data Filters

Data filters restrict which episodes are included in analysis. Changing a data filter changes every computed result.

Examples: opponent, map/mission, team size, episode date range.

### View Filters

View filters control which players' results are displayed. They do **not** change what is computed. The player
checkboxes in the sidebar are view filters — unchecking a player hides their data points, but the range (min/max) is
still computed across all players.

## Analysis Pipeline

Every analysis on the dashboard follows this pipeline. There are no exceptions.

### Step 1: Apply data filters to get the working episode set

```
filtered_episodes = [e for e in all_episodes if passes_all_data_filters(e)]
```

### Step 2: For each player, compute a per-player result

A "player" is any co-player or the primary policy being analyzed. For each player, collect their episodes from the
filtered set, then apply the analysis function.

```
player_results = {}
for player in all_players:
    player_episodes = [e for e in filtered_episodes if e.involves(player)]
    player_results[player] = analysis_fn(player_episodes)
```

The `analysis_fn` is whatever metric or aggregation the chart/card is computing (e.g., mean reward, junction count,
action success rate). It takes a list of episodes and returns a scalar.

### Step 3: Compute the range from all player results

The range is always min/max across **all** player results, regardless of view filters.

```
range_min = min(player_results.values())
range_max = max(player_results.values())
```

### Step 4: Apply view filters for display

View filters (player checkboxes) control which players' data points are rendered. The range does not change.

```
visible_players = [p for p in all_players if view_filter_checked(p)]
# render only visible_players' data points
# render range bar using range_min, range_max (always all players)
```

### Why this matters

If you compute the range from only the visible players, toggling a checkbox changes the scale of every chart. The range
must reflect the full filtered dataset so that hiding/showing players lets you compare against a stable baseline.

## Metrics Reference

### Episode-Level Metrics

| Metric   | Description         | Typical Range | Notes                 |
| -------- | ------------------- | ------------- | --------------------- |
| `steps`  | Episode length      | 500-10000     | Max varies by mission |
| `reward` | Total policy reward | 0-60          | Sum across all agents |

### Agent Action Metrics

Aggregated across all agents controlled by your policy. CogsGuard has three actions: `move`, `noop`, and `change_vibe`.

| Metric                       | Description                       | Typical Range | Good Value        |
| ---------------------------- | --------------------------------- | ------------- | ----------------- |
| `action.move.success`        | Successful movement actions       | 200-900       | >500              |
| `action.move.failed`         | Failed movement attempts          | 10-250        | <100              |
| `action.noop.success`        | No-operation actions              | 30-150        | Context-dependent |
| `action.change_vibe.success` | Successful vibe changes           | 0-50          | Context-dependent |
| `action.change_vibe.failed`  | Failed vibe change attempts       | 0-20          | <10               |
| `action.failed`              | Total failed actions              | varies        | Lower is better   |
| `action.timeout`             | Action timeouts (policy too slow) | 0-40          | <5                |
| `actions.swap`               | Successful agent swaps            | 0-20          | Context-dependent |

### Resource Metrics

Resources tracked with `.gained`, `.lost`, and `.amount` suffixes.

| Metric             | Description            | Typical Range | Notes                  |
| ------------------ | ---------------------- | ------------- | ---------------------- |
| `carbon.gained`    | Carbon collected       | 50-180        | Element resource       |
| `carbon.lost`      | Carbon deposited/used  | 10-70         |                        |
| `carbon.amount`    | Net carbon held        | 0-150         |                        |
| `oxygen.gained`    | Oxygen collected       | 10-50         | Element resource       |
| `oxygen.lost`      | Oxygen deposited/used  | 0-30          |                        |
| `oxygen.amount`    | Net oxygen held        | 0-50          |                        |
| `silicon.gained`   | Silicon collected      | 20-80         | Element resource       |
| `silicon.lost`     | Silicon deposited/used | 0-40          |                        |
| `silicon.amount`   | Net silicon held       | 0-80          |                        |
| `germanium.gained` | Germanium collected    | 0-50          | Rarer element          |
| `germanium.lost`   | Germanium deposited    | 0-30          |                        |
| `germanium.amount` | Net germanium held     | 0-50          |                        |
| `heart.gained`     | Hearts collected       | 3-20          | Required for alignment |
| `heart.lost`       | Hearts used/lost       | 0-15          |                        |
| `heart.amount`     | Net hearts held        | 0-20          |                        |

### Gear Metrics

| Metric             | Description            | Notes                       |
| ------------------ | ---------------------- | --------------------------- |
| `aligner.gained`   | Aligner gear pickups   | Enables junction alignment  |
| `aligner.lost`     | Aligner gear lost      |                             |
| `scrambler.gained` | Scrambler gear pickups | Enables junction scrambling |
| `scrambler.lost`   | Scrambler gear lost    |                             |

### Junction Metrics

| Metric                        | Description                       | Notes                   |
| ----------------------------- | --------------------------------- | ----------------------- |
| `junction.aligned_by_agent`   | Junctions aligned by our agents   | Primary junction metric |
| `junction.scrambled_by_agent` | Junctions scrambled by our agents |                         |
| `aligned.junction.gained`     | Collective junctions aligned      | During episode          |
| `aligned.junction.lost`       | Aligned junctions lost            | Scrambled by opponent   |
| `aligned.junction.held`       | Ticks junctions held aligned      | Stability measure       |

### Collective Metrics

| Metric                            | Description                     | Notes              |
| --------------------------------- | ------------------------------- | ------------------ |
| `collective.carbon.deposited`     | Carbon deposited to collective  | Team resource pool |
| `collective.oxygen.deposited`     | Oxygen deposited to collective  |                    |
| `collective.silicon.deposited`    | Silicon deposited to collective |                    |
| `collective.germanium.deposited`  | Germanium deposited             |                    |
| `collective.<resource>.withdrawn` | Resources withdrawn             |                    |
| `collective.<resource>.amount`    | Current collective inventory    |                    |

### Status Metrics

| Metric                            | Description                | Notes                      |
| --------------------------------- | -------------------------- | -------------------------- |
| `status.frozen.ticks`             | Ticks spent frozen         | From combat or environment |
| `status.max_steps_without_motion` | Max consecutive idle steps | Stuck detection            |

---

## Key Performance Indicators

### Tier 1: Primary Score Drivers

These metrics have the strongest correlation with tournament score:

1. **Junction Control** - `junction.aligned_by_agent`
   - Active junction manipulation is the biggest differentiator between top and bottom policies
   - Zero junction activity almost guarantees low scores

2. **Reward Distribution**
   - Consistent non-zero rewards beats occasional high scores
   - Target: >80% of episodes with reward > 0.1

3. **Average Reward**
   - Direct measure of policy quality
   - Bottom 50%: <1.0, Top 10%: 2.0-4.0, Elite: 4.0+

### Tier 2: Efficiency Metrics

4. **Resource Efficiency** - `sum(resource.gained)` / steps
   - Good: >0.1 resources per step
   - Indicates agents are gathering and not stuck

5. **Hearts-to-Junction Rate** - `junction.aligned_by_agent` / `heart.lost`
   - Efficiency of converting hearts to junction control
   - Good: >0.5 junctions per heart

6. **Reward Consistency** - `1 - (std/mean)` clamped 0-1
   - How consistent is reward across episodes
   - Good: >0.5

### Tier 3: Health Indicators

7. **Movement Success Rate** - `action.move.success` / (`action.move.success` + `action.move.failed`)
   - Good: >75%
   - Low rates indicate pathfinding issues or blocked paths

8. **Noop Rate** - `action.noop.success` / total_actions
   - Good: <15%
   - High rates indicate policy indecision or stuck states

---

## Diagnostic Patterns

### High movement failures + Low reward

**Diagnosis:** Pathfinding issue or blocked paths

- Agents may be stuck against walls or other agents
- Look for: movement success < 70%, `action.move.failed` > 100 per episode

### Zero junction activity + Non-zero hearts

**Diagnosis:** Aligner/scrambler not activating

- Policy acquires hearts but doesn't use them
- Check gear acquisition: does policy get aligner gear?
- May indicate goal-tree or decision logic bug

### High noop rate

**Diagnosis:** Policy indecision or stuck state

- `noop_rate` > 15% suggests policy frequently choosing to do nothing
- May indicate: unclear goals, navigation deadlock, or bug

### Matchup disparity

**Diagnosis:** Opponent-specific interaction issue

- Best opponent avg > 2.0 and worst opponent avg < 0.5
- Some opponent behaviors may break your policy's assumptions
- Check if low-scoring opponent has unusual behavior

### Declining rewards over episode index

**Diagnosis:** Learning/adaptation problem or meta-game shift

- If recent episodes score worse, may indicate:
  - Opponents adapted to your strategy
  - Bug introduced in recent policy version
  - Seasonal meta-game change

### High freeze time + Low reward

**Diagnosis:** Spending too much time frozen

- Episodes where frozen > 15% of steps AND reward < 50% of average
- Policy may be in contested territory too long
- Or: not retreating when at risk of being frozen

### High action timeouts

**Diagnosis:** Policy inference too slow

- `action.timeout` > 5 per episode indicates latency issues
- Policy may need optimization or simpler architecture

---

## Comparative Benchmarks

Based on top-10 leaderboard policies (as of current season):

| Metric             | Bottom 50% | Top 10% | Elite (#1-3) |
| ------------------ | ---------- | ------- | ------------ |
| Avg Reward         | <1.0       | 2.0-4.0 | 4.0+         |
| Junction Aligned   | <2         | 4-8     | 8+           |
| Move Success Rate  | <75%       | 80-85%  | 85%+         |
| Resource Total     | <150       | 200-300 | 300+         |
| Non-Zero Episode % | <40%       | 60-80%  | 90%+         |

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

---

## Dashboard Features

How the dashboard implements each analysis workflow from this guide.

### Debugging a Score Regression

| Workflow Step                | Dashboard Feature                                           |
| ---------------------------- | ----------------------------------------------------------- |
| Compare reward distributions | Overview tab: reward histogram + KPI cards                  |
| Check failure rate           | Failures tab: error breakdown chart + table                 |
| Compare behavioral metrics   | Overview tab: High/Low comparison table (top vs bottom 20%) |
| Identify changed matchups    | Co-players tab: click opponent row for metric comparison    |
| Review low-scoring episodes  | Episodes tab: sort by reward, expand for details            |

### Understanding a Bad Matchup

| Workflow Step                 | Dashboard Feature                                           |
| ----------------------------- | ----------------------------------------------------------- |
| Segment by opponent           | Co-players tab: click opponent row to filter                |
| Compare metrics vs overall    | Co-players tab: opponent comparison panel (>2x highlighted) |
| Check team composition        | Overview tab: Team Composition cards                        |
| Watch replay of worst episode | Episodes tab: sort by reward ascending                      |

### Identifying Behavioral Gaps

| Workflow Step                  | Dashboard Feature                                                   |
| ------------------------------ | ------------------------------------------------------------------- |
| Benchmark against top policies | Overview tab: Benchmarks table (Bottom 50% / Top 10% / Elite tiers) |
| Check role coverage            | Behavior tab: Strategy Profile radar chart                          |
| Analyze high vs low episodes   | Overview tab: High/Low comparison with >2x gap highlighting         |
| Look for zero-count metrics    | Behavior tab: Unused Capabilities banner                            |

### Diagnostic Patterns

All diagnostic patterns from this guide are auto-detected and shown in the Overview tab's diagnostic panel. Click any
diagnostic to see affected episodes:

- High movement failures
- Action timeouts
- High noop rate
- Matchup disparity
- Declining rewards
- High freeze time + low reward
- Zero junction alignment
- Unused capabilities (zero-count detection)
