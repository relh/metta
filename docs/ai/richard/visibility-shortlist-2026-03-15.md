# Shortlist of Things Good for Visibility

Date: 2026-03-15.

This note interprets the Asana task `Shortlist of things good for visibility` as: identify the existing repo surfaces
that do the best job of showing current progress, quality, and activity without needing a lot of internal context.

## What "good for visibility" means here

A strong visibility surface should do most of the following:

- show something current or live rather than static plans
- summarize the state clearly enough for a human or agent to orient quickly
- link to enough evidence that the summary feels credible
- be easy to access or embed
- reflect real product or training progress, not just internal plumbing

## Recommended shortlist

### 1. Single-policy dashboard (`policy-dashboard`)

This is the strongest overall visibility surface today. The backend route
`/policy-dashboard/v1/policies/versions/{policy_version_id}/data` assembles policy metadata, sampled episodes,
leaderboard context, version-over-version comparisons, matchup summaries, failure summaries, orchestration hooks, role
percentiles, and optional diagnose-run summaries. The frontend is already framed as the main standalone dashboard
surface and is designed to answer the core question "how good is this policy and what should we do next?"

Why it is good for visibility:

- broadest coverage in one place: outcomes, failures, coordination, capabilities, and trends
- can default to the current winner via `/policy-dashboard/v1/policies/versions/default/data`
- already positioned as the main single-policy analysis surface in Vibeservatory
- useful to both humans and LLM-style consumers because the payload is structured, not just visual

Main gap:

- it is high-value but not low-friction yet because it is Softmax-auth-facing and still assumes some tournament context

Repo signals:

- `vibeservatory/backend/dashboard_backend/policy_dashboard/router.py`
- `vibeservatory/README.md`
- `vibeservatory/iframe_surfaces.json`

### 2. Bardo

Bardo is the best live world-state surface. The backend route `/bardo/v1/world-state` returns generated time, visible
policies, active episode jobs, and canonical seasons. That makes it a strong answer to the question "what is happening
right now?" rather than "how good is one policy?"

Why it is good for visibility:

- live operational visibility into policies, active jobs, and seasons
- low conceptual overhead compared with deeper analysis surfaces
- useful as a control-room or status-wall surface
- naturally demoable because the data model is simple and current

Main gap:

- it shows activity and presence well, but not quality or diagnosis well

Repo signals:

- `vibeservatory/backend/dashboard_backend/bardo/router.py`
- `vibeservatory/README.md`
- `vibeservatory/iframe_surfaces.json`

### 3. Public stats API and docs surface

The public stats routes plus generated docs are the best programmatic visibility surface. The `/stats` routes expose
policies, policy versions, and episode queries with explicit public/private visibility rules, and the docs router makes
that contract inspectable. This is less visually impressive than the dashboard surfaces, but it is the cleanest path for
external tools, CLI flows, and LLM consumers that need structured data rather than screenshots.

Why it is good for visibility:

- lowest-friction path for external or automated consumers
- strong contract value because the public/private boundary is explicit
- good for "can others inspect and integrate with our system?" visibility
- complements the dashboard surfaces instead of competing with them

Main gap:

- it is more legible than exciting; it shows data access maturity more than product delight

Repo signals:

- `app_backend/src/metta/app_backend/routes/stats_routes.py`
- `app_backend/src/metta/app_backend/routes/docs_routes.py`
- `docs/specs/0024-public-api.md`

### 4. Cogames Diagnose

Diagnose is the best evidence-rich drill-down surface. The diagnose backend lists runs, serves structured artifacts, and
imports bundled diagnose outputs. The broader diagnose system already produces doctor notes, manifests, validity
artifacts, and replay bundles. That makes it one of the strongest surfaces for credible qualitative evaluation of a
specific policy.

Why it is good for visibility:

- high evidence density: not just scores, but artifacts and failure interpretation
- very useful when the audience wants to understand why a policy is weak or strong
- works as a trust-building surface because claims can be tied back to run artifacts

Main gap:

- it is a deep-dive surface, not the best default first impression

Repo signals:

- `vibeservatory/backend/dashboard_backend/diagnose/router.py`
- `docs/ai/cogames-diagnose-audit-2026-02-23.md`
- `docs/ai/cogames-diagnose-verification-2026-02-24.md`
- `vibeservatory/iframe_surfaces.json`

### 5. Pantheon

Pantheon is the best narrative visibility surface. It organizes behavior into fame / same / lame motif stories and is
the clearest current attempt to make policy behavior memorable rather than merely measurable. This is especially useful
for demos, storytelling, and explaining patterns that leaderboard numbers alone do not capture.

Why it is good for visibility:

- easiest surface for telling a concrete story about policy behavior
- good complement to the dashboard because it turns behavior into motifs
- likely useful for external narrative, qualitative comparison, and later retrieval/training workflows

Main gap:

- today it can fall back to seeded sample stories, so it is not yet as authoritative as the dashboard or Bardo

Repo signals:

- `vibeservatory/backend/dashboard_backend/pantheon/router.py`
- `vibeservatory/README.md`
- `docs/specs/0031-mettagrid-semantic-agent-layer.md`
- `vibeservatory/iframe_surfaces.json`

## Surfaces not in the top shortlist

### Trainboard

Trainboard is useful for internal training-pipeline visibility, but it is not one of the best first surfaces for broad
visibility. Its routes are focused on board state, task ranking, pipeline audit, and recompute behavior over a local
state dir. That makes it valuable for operators, but weaker as a default "show progress" surface for a wider audience.

Repo signals:

- `vibeservatory/backend/dashboard_backend/trainboard/router.py`

### Chatprop

Chatprop is mounted as a Vibeservatory surface, but from the current repo context it is less clearly the right answer to
this task than the dashboard, Bardo, Diagnose, Pantheon, or the public stats/docs surface.

Repo signals:

- `vibeservatory/backend/dashboard_backend/app.py`
- `vibeservatory/iframe_surfaces.json`

## Recommendation

If this task is asking for a practical shortlist to use in planning or demos, the best ordering is:

1. `policy-dashboard` as the main default progress surface
2. `Bardo` as the live status / world-state surface
3. public stats + docs as the programmatic visibility surface
4. `diagnose` as the evidence-rich drill-down surface
5. `Pantheon` as the narrative and behavior-story surface

That ordering covers the main visibility modes cleanly: summary, live status, API visibility, deep evidence, and
storytelling.
