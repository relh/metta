# Cogsguard: Batteries Included

> **Status:** Approved **Author:** Alex Smith **Created:** 2026-01-20

## Summary

Reduce the overhead for training competent models in Cogsguard so users can quickly see the value of participating in
training and the Alignment League Benchmark. Cogsguard should "work out of the box".

## Problem

A priori, you need to do a lot of work to successfully train a competent model in Cogsguard. A plausible list is:

- Figure out how to play
- Hook up your favorite RL infrastructure
- Do some reward densification to overcome sparse rewards and credit assignment problems
- Build a curriculum that matches your model's development
- Build multiple team mates so your policy has someone to play with
- Attach your favorite monitoring tools
- Figure out parallel training

## Goals

- Users should be able to onboard to Cogsguard and start playing and seeing the value within minutes of installing it
- Users should be able to train a policy that can be a useful part of a positively-scoring team within an hour
- Users should only need to bring their special sauce. They shouldn't need to reinvent anything commonplace
- User onboarding should teach users good long term behavior. Users may out-grow our tools, but we shouldn't be teaching
  them anything we know they're going to need to un-learn

## Design

### Baseline Agents

These agents are needed both for training (as teammates/opponents) and for users to be able to play and understand the
game.

- **Baseline Miner** - harvests and deposits
- **Baseline Scrambler** - disrupts nearest enemy junction
- **Baseline Aligner** - captures nearest neutral junction

**Bonus:** Agents perform basic communication:

- Vibes to communicate what you're going to do
- Vibes to communicate what you think needs to be done

### Curricula

**MVP:** A curriculum that can train an aligner that scores points on a team with baseline miners + scramblers.

**Bonus:** Curricula for miners and scramblers.

Curricula need:

- **Training environment:** Cogsguard configured for the specific skill. E.g., the agent already equipped with the
  correct gear, Clips enabled / disabled as appropriate. Junctions aligned or not.
- **Shaped rewards:** Reward function tuned to that skill. E.g., for basic harvesting: reward for resources collected /
  deposited.
- **Allies doing complementary roles:** Baseline agents filling other roles so the trainee has a functioning team
  context

### Integrations for Training

We believe we already have this covered:

- Notebooks with training recipes
- Gym / PettingZoo environment wrapper
- Logging integrations (WandB, TensorBoard)
- Vectorized environment support for parallel training

### Skills

These are skills to consider when building curricula.

#### Miner Skills

- Harvesting and returning resources to an aligned junction/hub
- Choosing which resource to harvest based on team need
- Collective mining to harvest more efficiently
- Harvesting in neutral / enemy territory

#### Scrambler Skills

- Disrupting a single enemy junction
- Disrupting multiple junctions with breaks for recovery
- Avoiding junctions that would drain HP before arrival
- Prioritizing which junction to disrupt

#### Aligner Skills

- Capturing neutral junctions
- Waiting for Scramblers to neutralize before advancing
- Prioritizing which junction to capture

#### Scout Skills

- Exploring the map efficiently
- Identifying high-value targets (undefended junctions, resource clusters)
- Surviving in contested/enemy territory (using HP/energy pool)
- Relaying information (if there's a communication mechanism) or positioning to enable team action

#### Team Coordination Skills

- Picking a role to fill the team's need
- Switching roles in response to game state
- Scrambler-Aligner sequencing (disrupt then capture)
- Territorial defense (responding to Clips expansion or enemy incursion)
- Collective prioritization (which junction to attack/defend as a team)

## Open Questions

1. What level of baseline agent competence is sufficient for MVP?
2. How do we measure "useful part of a positively-scoring team"?
