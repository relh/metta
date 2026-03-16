# Richard's Active Tasks

Snapshot date: 2026-03-15.

This is a repo-grounded reading of the 21 open Asana tasks currently assigned to Richard. I pulled the task list via
`gastown/scripts/asana_sync.py --scope my --json`, then read nearby specs, docs, tests, and code to infer what each task
most likely means in the current codebase. Confidence is high when the title or project maps directly to existing
artifacts, and lower when the Asana card is title-only or appears to be a planning placeholder.

## Quick read

- Overdue tasks: `Tejaswi Cheella`, `Review Trained Based Roles`, and `Successor Features`.
- The strongest current clusters are: role-specialist baselines and competitor bots, curriculum/autocurricula,
  observability and dashboard surfaces, Vibeservatory surfaces (`Bardo`, `Pantheon`), and some hiring/admin cleanup.
- Several tasks are clearly active ideas but are still underspecified from repo context alone. Those are called out
  explicitly rather than being over-interpreted.

## Overdue and current-focus tasks

### [Tejaswi Cheella](https://app.asana.com/1/1209016784099267/project/1211414414907311/task/1213220544077198)

Due: 2026-02-12. Project: `contractor-hiring-pi / resume-screen`. Confidence: high.

This is a hiring-pipeline resume screen, not a product or research task. The repo already has a concrete screening
rubric and a dedicated `hr.screen-resumes` skill, so the likely work here is to evaluate this candidate against the
team's actual bar: hard systems caliber, real AI/ML relevance, Softmax-specific motivation, and whether the profile is
strong enough to justify interview time. In practice this means turning the application into a clear advance / lean
advance / reject decision with a short rationale.

Repo signals: `docs/resume-screen-rubric.md`, `skills/hr.screen-resumes/SKILL.md`

### [Review Trained Based Roles](https://app.asana.com/1/1209016784099267/task/1213496449865944)

Due: 2026-03-06. Project: unfiled. Confidence: medium-low.

I do not see an exact title match in the repo, but it sits next to `Scripted Base Roles` and the strongest adjacent work
is the recent role-specialist baseline push for miner / scout / aligner / scrambler. My read is that this task is about
reviewing the learned role baselines: checking whether the isolated role train commands, evals, and mixed-team transfer
checks are producing useful "trained base roles" rather than just runnable commands. Put differently, this looks like an
audit of whether the trained role-specialist stack is actually good enough to serve as a foundation for later bots or
curriculum work.

Repo signals: `docs/experiments/cogsguard_role_specialists_runbook_2026-02-24.md`,
`docs/ai/cogsguard-role-specialists-pr-update-2026-02-24.md`

### [Successor Features](https://app.asana.com/1/1209016784099267/project/1209041170403490/task/1213434761500088)

Due: 2026-03-06. Project: `training/rl-infrastr / roadmap`. Confidence: high.

This clearly matches the current dense-future-attribute-prediction versus successor-feature / diff-horde comparison in
the CogsGuard training stack. The repo already has a dedicated parity spec that compares `FutureAttributePredictionLoss`
against `DiffHordeLoss`, plus recipe wiring for both framings and notes about stabilization sweeps, cumulant packs, and
teacher-first evaluation. The practical job here appears to be making the successor-feature path train stably enough to
be compared honestly against the dense baseline, then deciding whether the SF framing is worth carrying forward.

Repo signals: `docs/specs/0030-successor-features-parity.md`, `recipes/experiment/cogsguard_fap.py`,
`recipes/experiment/cogsguard.py`, `metta/rl/loss/diff_horde.py`, `metta/rl/loss/future_attribute_prediction.py`

### [Autocurricula](https://app.asana.com/1/1209016784099267/project/1213471594342425/task/1213441685618447)

Project: `thread-roadmap / march--2026:-rapid-b`. Confidence: high.

This maps directly onto the tree-based curriculum work Richard has already been driving: decompose game mechanics into
atomic nodes, join them back into higher-order skills, evaluate readiness per node, and then use that structure to drive
training. The spec already describes a canonical CogsGuard training tree, join-based curricula, node-level evals, and an
Observatory-facing readiness view, while the curriculum code already has task pools, learning-progress scoring, and even
a `tree_curriculum` helper. So this task looks like "turn the curriculum from a flat bag of tasks into an explicit
mechanic tree that both training and evaluation understand."

Repo signals: `docs/specs/0027-cogsguard-training-tree-autocurricula.md`,
`metta/cogworks/curriculum/tree_curriculum.py`, `metta/cogworks/curriculum/curriculum.py`,
`metta/cogworks/curriculum/learning_progress_algorithm.py`

### [Improve Single-Policy Observatory UX (LLM Consumable Stats)](https://app.asana.com/1/1209016784099267/project/1213471594342425/task/1213483513742821)

Project: `thread-roadmap / march--2026:-rapid-b`. Confidence: high.

This is about making the single-policy analysis surface readable by agents and not just humans clicking around a GUI.
The repo already has a single-policy dashboard workflow that pulls episode stats, failure patterns, matchup breakdowns,
and behavior metrics into a self-contained dashboard, plus Vibeservatory dashboard tabs that aggregate policy KPIs and
diagnose outputs. The task therefore reads less like "make another dashboard" and more like "normalize the important
policy stats into machine-usable summaries and contracts so LLMs or competitor bots can consume them without scraping ad
hoc UI."

Repo signals: `skills/cg.policy-dashboard/skill.md`, `vibeservatory/README.md`,
`tests/vibeservatory/backend/test_iframe_surface_contract.py`,
`app_backend/src/metta/app_backend/routes/stats_routes.py`

### [Autogames: Add more mettagrid games to free play](https://app.asana.com/1/1209016784099267/project/1213471594342425/task/1213598414224898)

Project: `thread-roadmap / march--2026:-rapid-b`. Confidence: medium.

There is no direct `autogames` module yet, but the repo already has the ingredients for it: a generic game-construction
guide in CoGames, tournament support for evergreen freeplay seasons, and season/versioning infrastructure that can host
different game rule sets over time. My best read is that this task is about expanding the submit-and-evaluate loop so
more Mettagrid-based games, not just the current CogsGuard-centric setup, can be played in a lightweight freeplay
season. That likely means new missions/games on the CoGames side plus season or commissioner work on the Observatory
side.

Repo signals: `packages/cogames/MAKING_A_COGAME.md`, `packages/cogames/README.md`,
`app_backend/src/metta/app_backend/routes/tournament_routes.py`, `docs/specs/0020-season-versions.md`

### [Pull out the make game skills](https://app.asana.com/1/1209016784099267/task/1213602184360701)

Project: unfiled. Confidence: low.

There is no exact repo hit for this title, so this is an inference from adjacent work. The codebase already contains a
clear human guide for building a new CoGame and a large skills registry for teaching agents repeatable workflows; this
task most plausibly means extracting the tacit "how to make a game" knowledge into reusable skills, templates, or
helpers instead of leaving it buried in docs and game-specific code. Another plausible reading is that it means pulling
game-construction abstractions out of one specific project and making them generic, but either way the theme looks like
codifying game-building as a reusable capability.

Repo signals: `packages/cogames/MAKING_A_COGAME.md`, `docs/ai/skills.md`, `skills/`

## Thread-roadmap backlog and adjacent surfaces

### [Bardo](https://app.asana.com/1/1209016784099267/project/1213471594342425/task/1213548416918439)

Project: `thread-roadmap / backlog-/-blocked`. Confidence: high.

`Bardo` already exists in the repo as a standalone Vibeservatory surface backed by a `/bardo/v1/world-state` API that
shows policies, active jobs, and canonical seasons. The current code is about assembling a live "lobby/world state" view
over Observatory data, with filtering, auth, caching, and a cap on visible policies so the screen stays legible. So this
task looks like further productization of that world-state surface: either richer operational visibility, UI polish, or
unblocking the remaining data-quality issues so Bardo becomes a dependable control-room view.

Repo signals: `vibeservatory/README.md`, `vibeservatory/backend/dashboard_backend/bardo/router.py`,
`tests/vibeservatory/backend/bardo/test_router.py`

### [Pantheon (Trajectory Bank)](https://app.asana.com/1/1209016784099267/project/1213471594342425/task/1213533800795729)

Project: `thread-roadmap / backlog-/-blocked`. Confidence: high.

This matches the existing `Pantheon` dashboard surface very closely: a hall-of-fame / same / lame story bank built from
replay-derived motifs. The backend already serves seeded or file-backed motif stories from `outputs/pantheon`, and the
semantic-agent-layer spec explicitly talks about trajectory analysis and motif extraction as an explanation layer above
aggregate scores. So the likely end state is not just a pretty page; it is a replay-mined trajectory bank that can both
explain behavior and potentially feed supervised or retrieval-based learning later on.

Repo signals: `vibeservatory/README.md`, `vibeservatory/backend/dashboard_backend/pantheon/router.py`,
`tests/vibeservatory/backend/pantheon/test_router.py`, `docs/specs/0031-mettagrid-semantic-agent-layer.md`

### [Stats Page/UI Design](https://app.asana.com/1/1209016784099267/project/1213471594342425/task/1213498087554525)

Project: `thread-roadmap / february-2026:-al-&-`. Confidence: high.

This looks like the UI-design companion to the more product-level "LLM consumable stats" task above. The repo already
has a policy-dashboard tool that organizes episodes, opponents, behavior, failures, and overview KPIs, plus a standalone
Vibeservatory dashboard with multiple tabs and embedded diagnose/capability views. So this task most likely is not
deciding what metrics exist; it is deciding how the single-policy page should actually present them so a human or agent
can quickly understand what a policy is good at, what breaks, and what to do next.

Repo signals: `skills/cg.policy-dashboard/skill.md`, `vibeservatory/README.md`, `devops/charts/softmax-com/values.yaml`,
`tests/vibeservatory/backend/test_iframe_surface_contract.py`

### [Cogames Diagnose](https://app.asana.com/1/1209016784099267/project/1213471594342425/task/1213498087554526)

Project: `thread-roadmap / february-2026:-al-&-`. Confidence: high.

This is one of the clearest tasks in the set because there are already audit and verification writeups around the
current diagnose system. `cogames diagnose` is now a staged doctor-visit pipeline with Stage 1 individual review, Stage
2 social review, strict artifact bundles, replay evidence, and a dashboard surface that renders symptoms, prescriptions,
and capability probes. The remaining work appears to be finishing the product contract: clean metrics, correct dashboard
presentation, strict pack validity, and better surfacing of the social and evidence context.

Repo signals: `packages/cogames/src/cogames/diagnose.py`, `docs/ai/cogames-diagnose-audit-2026-02-23.md`,
`docs/ai/cogames-diagnose-verification-2026-02-24.md`

### [Scripted Base Roles](https://app.asana.com/1/1209016784099267/project/1213471594342425/task/1213498087554528)

Project: `thread-roadmap / february-2026:-al-&-`. Confidence: high.

This appears to be the scripted-baseline half of the role-specialist track. The repo already has a canonical scripted
role policy URI, a teacher/supervisor pipeline that can feed scripted actions into training, and diagnose support for a
`--scripted-baseline-policy` reference policy. That suggests the task is to make the role-based scripted policies
explicit, reliable, and evaluatable enough that they can serve as both baselines and supervision sources for learned
agents.

Repo signals: `metta/rl/training/teacher.py`, `tests/rl/test_supervised_scripted_actions.py`,
`docs/experiments/cogsguard_role_specialists_runbook_2026-02-24.md`, `packages/cogames/src/cogames/diagnose.py`

### [AI Competitor Bot](https://app.asana.com/1/1209016784099267/project/1213471594342425/task/1213498087554522)

Project: `thread-roadmap / february-2026:-al-&-`. Confidence: medium-high.

The repo language around "competitor bot" shows up most clearly in the AI researcher workflow, where neophyte and
experienced competitor bots are launched as branch jobs that run a train / upload / submit / diagnose loop against a
tournament season. My read is that this task is about turning one of those workflows into a concrete, competitive,
continuously-improving bot rather than leaving it as a runbook or prompt scaffold. That makes it adjacent to
`Scripted Base Roles`, `Review Trained Based Roles`, and the dashboard/diagnose tasks because those are the surfaces a
competitor bot would use to train, submit, evaluate, and introspect itself.

Repo signals: `docs/ai/ai-researcher-workflows-runbook.md`,
`docs/experiments/cogsguard_role_specialists_runbook_2026-02-24.md`

## Infrastructure and platform tasks

### [Shortlist of things good for visibility](https://app.asana.com/1/1209016784099267/task/1213247155039757)

Project: unfiled. Confidence: low.

This title is too vague to anchor to one code path, but "visibility" in the current repo mostly means externally or
internally legible surfaces: public stats endpoints, tournament season summaries, dashboard tabs, Bardo, Pantheon, and
other demoable artifact views. So the likely task is to compile a list of product surfaces that best show progress to
humans, not to build a new subsystem from scratch. I would treat this as a curation and prioritization task across the
existing Observatory / Vibeservatory surfaces rather than a single implementation ticket.

Repo signals: `vibeservatory/README.md`, `app_backend/src/metta/app_backend/routes/stats_routes.py`,
`app_backend/src/metta/app_backend/routes/docs_routes.py`, `docs/specs/0024-public-api.md`

### [Mettaboxes](https://app.asana.com/1/1209016784099267/project/1211365635533653/task/1210397100757356)

Project: `ep2-training/rl-infr / infrastructure`. Confidence: high.

`Mettaboxes` are the named remote GPU boxes (`metta0` through `metta4`) used for launching, inspecting, and profiling
training runs. The repo already treats them as a first-class operator surface with a dedicated CLI for run, audit,
instrument, tmux attach, and even container-restart recovery, and adjacent Asana cache entries mention one-click reboot
and GUI ideas. So this task likely covers improving the operator experience around those boxes: making status, launch,
recovery, and maybe reboot workflows easier and more visible.

Repo signals: `skills/do.mettabox-ops/SKILL.md`, `devops/mettabox/cli.py`, `trainboard/data/asana_research_cache.ndjson`

### [Turn Principal Software Engineer doc into an Applied Research Scientist](https://app.asana.com/1/1209016784099267/task/1213130586079164)

Project: unfiled. Confidence: low.

This looks like a hiring-doc rewrite task rather than a code task. The repo does not expose the exact source document,
but the surrounding hiring materials make clear that Softmax wants a blend of systems depth, AI/RL fluency, and
research-style judgment rather than a generic product engineer profile. So the likely work is to rewrite an existing job
description so it describes the actual operating model here: experimentation, training infrastructure, multi-agent-RL
intuition, and willingness to reason from metrics and artifacts instead of just shipping CRUD features.

Repo signals: `docs/resume-screen-rubric.md`, `skills/hr.screen-resumes/SKILL.md`

## Research and curriculum tasks

### [Curriculum](https://app.asana.com/1/1209016784099267/project/1212315371281408/task/1212315371281446)

Project: `design-docs / untitled-section`. Confidence: high.

The Asana notes here already ask the right question: what should curriculum mean once you account for hand-designed
progressions, autocurricula, distributed training, and opponent choice? The repo has a mature curriculum substrate with
task pools, learning-progress and regret-style algorithms, tree-based generators, and recipe wiring into CogsGuard, but
it still mostly treats tasks as flat IDs rather than semantically structured mechanics. So this task looks like the
higher-level design umbrella over the more concrete `Autocurricula`, task-pool-scaling, and explore/exploit tasks.

Repo signals: `metta/cogworks/curriculum/curriculum.py`, `metta/cogworks/curriculum/learning_progress_algorithm.py`,
`metta/cogworks/curriculum/tree_curriculum.py`, `recipes/experiment/cogsguard.py`

### [characterize explore versus exploit in scores](https://app.asana.com/1/1209016784099267/project/1211365505625994/task/1211745249177397)

Project: `cybernetics / adaptive-curriculum`. Confidence: medium-high.

This appears to be an analysis task over the curriculum scoring signals rather than a brand-new algorithm. The current
learning-progress and prioritized-regret code already encode explicit exploration bonuses and exploitation pressure, and
the repo has metric descriptions and example recipes that expose those tradeoffs numerically. So the likely deliverable
is a sharper understanding of how the score signals behave: when a task is being revisited because it is genuinely
learning-rich versus when the system is merely exploiting a familiar task that looks good on paper.

Repo signals: `metta/cogworks/curriculum/learning_progress_algorithm.py`,
`metta/cogworks/curriculum/prioritized_regret_algorithm.py`, `recipes/experiment/regret_examples.py`,
`common/src/metta/common/wandb/docs/metric_descriptions.yaml`

### [Characterize task pool size scaling relative to number of envs](https://app.asana.com/1/1209016784099267/project/1211365505625994/task/1211413561080883)

Project: `cybernetics / adaptive-curriculum`. Confidence: high.

This is a concrete curriculum-systems question: how the active task pool and the number of simultaneous environments
interact, especially around duplicate sampling and the quality of the learning-progress distribution. The curriculum
core always keeps a fixed-capacity task pool, and the LP algorithm stores per-task history and can evict low-value
tasks, so pool size directly changes both exploration pressure and statistical stability. The task likely asks for a
scaling characterization of that system: what happens to overlap, LP score distribution, and useful diversity as the
number of envs grows.

Repo signals: `metta/cogworks/curriculum/curriculum.py`, `metta/cogworks/curriculum/learning_progress_algorithm.py`,
`tests/cogworks/curriculum/test_curriculum_algorithms.py`, `docs/specs/0027-cogsguard-training-tree-autocurricula.md`

### [implement v0 context embedding via environment conditioned initial LSTM state](https://app.asana.com/1/1209016784099267/project/1209185339447618/task/1210588759331356)

Project: `sprints / july-28---aug-1`. Confidence: medium.

I do not see this exact experiment in the repo, but the title lines up with the recurrent-policy stack very cleanly.
Today the stock LSTM policy initializes agent hidden state to zeros, and the generic policy API assumes that initial
state comes from `initial_agent_state()`; this task sounds like changing that contract so the initial recurrent state is
conditioned on environment identity or class rather than being blank. In practical terms that would give the policy an
environment-level context prior at timestep zero, which fits the Asana description of avoiding an
observation-to-environment bottleneck without having to stuff all context into normal per-step observations.

Repo signals: `packages/mettagrid/python/src/mettagrid/policy/lstm.py`,
`packages/mettagrid/python/src/mettagrid/policy/policy.py`, `packages/cortex/README.md`

## Lower-signal or placeholder tasks

### [Make it good](https://app.asana.com/1/1209016784099267/task/1212078048284634)

Project: unfiled. Confidence: very low.

This title is too underspecified to recover from repo context alone. The most honest reading is that it is a placeholder
for a later quality pass on some other initiative, not a self-contained task with a uniquely identifiable code path. If
this is meant to be actionable, it needs a linked doc, branch, or project area before someone can do more than make up
plausible interpretations.

Repo signals: none stronger than the general quality / polish work spread across the repo

## Tasks that likely belong to the same roadmap cluster

The following four tasks look like one coherent thread rather than four unrelated tickets:

- `Review Trained Based Roles`
- `Scripted Base Roles`
- `AI Competitor Bot`
- `Cogames Diagnose`

My best read is that this cluster is about building a pipeline from baseline role behavior -> trained role specialists
-> automated competitor bots -> diagnosis and dashboard feedback.

Likewise, these appear to be one product-and-research cluster:

- `Autocurricula`
- `Curriculum`
- `characterize explore versus exploit in scores`
- `Characterize task pool size scaling relative to number of envs`
- `Successor Features`

That cluster is about making the training loop more sample-efficient and more interpretable by structuring tasks,
choosing what to learn next, and adding better prediction targets.
