# Hunger Games - Rules

## Overview

Predator-prey survival game with seasonal cycles. Agents choose a role, forage or hunt for food, and try to hatch eggs
through harsh winters.

## Roles

At the start of the episode, agents visit a gear station to lock in their role. Once chosen, roles cannot be changed.

- **Prey**: Can harvest food from plants. Cannot tag anyone. Nimble (small energy pool, fast regen).
- **Predator**: Can tag prey to steal all their food. Can tag other predators (both lose egg). Cannot harvest plants.
  Bursty (large energy pool, slow regen).

## Food

Food is the survival currency. All agents lose food periodically. If an agent's food reaches zero while carrying an egg,
they lose the egg.

- **Prey** get food by tapping plants.
- **Predators** get food by tapping prey (steals all the prey's food, capped at 100).
- **Predators cannot** get food from plants.

## Plants

Plants are scattered across the map. They regenerate food over time via seasonal events. Each regen cycle, a random
subset of plants receives food -- not all plants at once. Agents must explore to find replenished plants.

Plants produce more food during the day and less at night. Food production varies by season: abundant in summer, scarce
in winter.

## Seasons

The year is 1000 ticks, divided into 4 seasons of 250 ticks each. The episode runs for 5000 ticks (5 full years).

| Season     | Effect                                                      |
| ---------- | ----------------------------------------------------------- |
| **Summer** | Plants produce lots of food. Agents forage and gear up.     |
| **Fall**   | All agents receive an egg. Plant food production decreases. |
| **Winter** | Plants produce almost no food. Maximum survival pressure.   |
| **Spring** | Agents still carrying an egg get a reward. Egg is removed.  |

## Eggs

- Distributed to all agents at the start of each fall.
- If an agent makes it to spring still carrying an egg, the egg hatches (reward).
- An agent **loses their egg** if:
  - Their food reaches zero (starvation).
  - They are tagged by a predator (prey only).
  - They tag or are tagged by another predator (both lose egg).

## Day/Night Cycle

Each day is 50 ticks (~5 cycles per season). Affects both energy and plants.

- **Day**: Agents regen energy faster (+2 solar). Plants produce bonus food.
- **Night**: Agents regen energy at base rate. Plants produce only base food.

Predators are especially slow at night (solar drops to 1). Prey can still move reasonably well (solar 3). This makes
nighttime safer for prey.

## Energy

Energy is consumed by movement. When energy runs out, the agent cannot move.

|               | Prey | Predator |
| ------------- | ---- | -------- |
| Energy pool   | 30   | 100      |
| Solar (day)   | 5    | 3        |
| Solar (night) | 3    | 1        |
| Move cost     | 4    | 4        |

## Scoring

Agents are rewarded for hatching eggs. Over 5 years, a skilled agent can hatch up to 5 eggs.
