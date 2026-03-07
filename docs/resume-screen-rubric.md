# Resume Screen Rubric

## Context

Softmax is an AI alignment company focused on multi-agent reinforcement learning, evolutionary-inspired alignment, and
AI safety. The tech stack is Python and C++. The team builds grid-based game environments where AI agents learn
cooperation. The role is **Software Engineer**.

This rubric was derived from analyzing 16 real screening decisions (6 advanced, 10 rejected) made by the hiring captain,
examining the full application materials (resume, application responses, comments).

---

## Rubric

### Overview

The resume screen must **never miss a great candidate**, but should reject merely okay ones and accept the risk of
occasionally losing a good-not-great candidate in the process. Given the volume of applications relative to the team's
capacity for calls, a strong signal is required to advance — not just the absence of red flags.

### Evaluation Dimensions

#### 1. Technical Caliber (Resume)

What to look for:

- **Top-tier company experience in relevant domains**: DeepMind, Google Research, Apple AI/ML, OpenAI, Anthropic, FAIR,
  etc. This is a very strong signal on its own.
- **Depth over breadth**: Building novel systems (new algorithms, architectures, protocols) vs. assembling existing
  components ("putting AWS legos together"). Look for work that required invention, not just integration.
- **Systems-level engineering**: C++, Rust, performance-critical code, low-level systems work. Python-only or JS-only
  backgrounds are weaker (but not disqualifying if other signals are strong).
- **Publications, patents, or SOTA results**: Accepted papers, especially at top ML venues. Patents for novel
  techniques. Demonstrated research capability.
- **Founding/early-stage experience**: Building 0-to-1 at a startup, especially in a technical domain, shows initiative
  and ownership.

Red flags:

- Only integration/glue work (connecting APIs, cloud services, CRUD apps)
- Multiple sub-year jobs without clear narrative
- Resume lists many technologies but accomplishments are shallow
- No evidence of building anything novel or technically challenging
- Bootcamp-only education with no compensating exceptional work
- Jargon-heavy resume that is self-promotional but lacks evidence of hard engineering (e.g. claiming to "contribute to
  $9B in revenue" or listing AI buzzwords without concrete technical accomplishments that demonstrate depth)

#### 2. AI/ML Relevance (Resume + Application)

What to look for:

- **Direct AI/ML work**: Training models, building ML infrastructure, interpretability, post-training, computer vision,
  NLP, reinforcement learning
- **Alignment/safety connection**: Work on LLM security, interpretability, model evaluation, robustness, data quality
  for AI systems
- **RL or games connection**: Multi-agent systems, game environments, simulation platforms, evolutionary algorithms --
  directly relevant to Softmax's work
- **Research background in relevant fields**: ML, RL, computational neuroscience, complex systems, game theory

Red flags:

- Background entirely unrelated to AI (pure web dev, network engineering, DevOps) with no demonstrated interest or
  self-study
- Academic background in an unrelated field (astrophysics, etc.) without clear bridge to Softmax's work -- especially
  combined with visa requirements

#### 3. Application Quality ("Why Softmax?" + "Proud of" + "Analytical Rigor")

What to look for:

- **Softmax-specific enthusiasm**: Demonstrates understanding of what Softmax does (multi-agent RL, alignment, game
  environments). References the company's approach, not just "AI is important."
- **Thoughtful "proud of" answer**: Tells a story that reveals curiosity, ownership, and going deep. The best answers
  describe inventing something, not just building to spec.
- **Genuine analytical rigor example**: Shows independent thinking, questioning assumptions, finding root causes. Not a
  canned answer.
- **Philosophical engagement with alignment**: Candidates who think deeply about why alignment matters and have their
  own perspective, not just buzzwords.

Red flags:

- Generic "why interested" that could apply to any AI company ("AI is the future", "I want to work on hard problems")
- One-line or minimal-effort answers -- signals the candidate is mass-applying
- Application reads as templated / mass-applied: answers that could apply to any company, suspiciously similar phrasing
  to other applications (e.g. the "we wanted to scale horizontally, but I profiled and found the real bottleneck" story
  has appeared in multiple applications verbatim)
- "Why interested" reads like a cover letter about themselves rather than about Softmax
- Delusional confidence ("I can solve the hardest problems in AI") without institutional validation

#### 4. Visa Status

- **No sponsorship needed**: Standard bar applies.
- **OPT/STEM OPT (no employer sponsorship)**: Standard bar applies.
- **Requires employer sponsorship (TN, E-3, O-1, H-1B)**: Bar is meaningfully higher. The candidate needs a clearly
  stronger profile to justify the additional cost and complexity.

#### 5. Referral / Source Signal

- **Known referral from team member or investor**: Strong positive signal. Can compensate for a weaker-looking
  application if the referrer has direct context on the candidate's abilities.

---

### Decision Framework

**ADVANCE** if the candidate has **at least one strong signal** of:

1. Worked at a top-tier AI/ML org (DeepMind, Google Research, Apple AI, OpenAI, Anthropic, FAIR, etc.) in a relevant
   role
2. Has published ML research or built novel ML systems (not just used APIs)
3. Maintains or significantly contributes to a major open-source project (hundreds of stars, real architectural
   contributions -- not surface-level PRs)
4. Application shows deep, specific enthusiasm for Softmax's mission AND the resume shows they can back it up
   technically
5. Has a strong referral from someone the team trusts
6. Application tells a story that reveals exceptional curiosity, depth, and 0-to-1 building ability -- even if their
   background is unconventional

The signal must be **concrete and verifiable** -- not just jargon or self-promotion. "Worked on AI" is not a signal;
"built a neuroevolution pipeline that generated synthetic training data" is.

**AND** none of the hard-reject criteria below apply.

**LEAN ADVANCE** only if there is a real positive signal but with notable concerns. This is not a parking spot for
candidates you're unsure about -- there must be something specific that makes the candidate worth a call, and the
concerns should be things an interviewer can resolve in 30 minutes.

**REJECT** if:

1. Application is low-effort (one-line answers, no Softmax-specific content, clearly mass-applying)
2. Background has zero connection to AI/ML/RL and the application doesn't demonstrate credible self-study or transition
3. Resume shows only integration/glue work with no evidence of building novel systems
4. Requires visa sponsorship AND doesn't meet any of the advance criteria especially strongly
5. Candidate shows delusional confidence without institutional or peer validation
6. Resume shows a pattern of very short tenures (multiple sub-year roles) without explanation
7. Resume is jargon-heavy and self-promotional but lacks concrete evidence of hard engineering -- the candidate may have
   worked _around_ AI without doing technically deep work themselves

**LEAN REJECT** for candidates who have some positive qualities but no signal strong enough to justify a call. This is
the default for "decent but not compelling" candidates. Given application volume, it is better to reject a merely good
candidate than to spend limited interview time on them.

**BORDERLINE** cases: Only advance if you would be genuinely surprised to learn the candidate was a bad fit. If the
reaction is "maybe they're fine," that's a reject -- the bar is "this person might be great."

---

### Calibration Examples

#### Clear Advances

- **DeepMind engineer** who worked on interpretability and post-trained Gemini. Top-tier org + directly relevant AI
  work. Easy yes.
- **Apple AI/ML engineer** who architected LLM tool authentication and has thoughtful alignment philosophy. Top-tier
  org + relevant work + philosophical depth.
- **OSS maintainer** of a framework with 870+ stars and 20M downloads, with strong Softmax-specific excitement. Major
  OSS impact + genuine enthusiasm.

#### Borderline Advances

- **Semiconductor engineer** with CNN/GNN research and IEEE publication but mostly codes in Node.js/C#. Advance because
  ML research background is real, but flag the language mismatch for the call.
- **Engineer with a compelling 10-year-old story** about building esports analytics in C at age 14, but gaps in recent
  work history. Advance because the story shows curiosity and drive, but note skepticism about recency.
- **Engineer referred by an insider** whose application doesn't strongly match the role. Advance on referral signal, but
  note the mismatch for the interviewer.

#### Clear Rejects

- **Bootcamp grad** working at Costco, built a video search pipeline by connecting AWS services. OSS contributions are
  surface-level UI fixes. No AI/ML depth.
- **Astrophysicist** with NeurIPS paper in genomics but no clear connection to Softmax's work AND requires visa
  sponsorship. Interesting background but too far from the role.
- **Undergrad intern** at AWS with a single internship, projects are classroom-level (CRUD app, shell implementation),
  generic application. Not enough signal.
- **Self-taught engineer** with 4-page resume and claims of "8+ years industry-level AI/ML R&D" but only contract work
  and self-directed projects with no institutional validation. "Delusionally confident."
- **15-year veteran in network analytics** with zero AI connection and a generic "looking for high-impact systems work"
  application. Experience is real but entirely irrelevant.
- **Generic backend engineer** whose "analytical rigor" example is the standard "profiled instead of scaling
  horizontally" story and whose application has no Softmax-specific content.
- **AI-adjacent engineer** with jargon-heavy resume (mentions multi-agent AI, neuroevolution, etc.) but work is
  self-promotional without clear evidence of hard engineering. "Why Softmax?" is generic. Having AI buzzwords on your
  resume is not the same as having done deep technical AI work. Reject.

---

## Appendix: Evidence Base

### Signals that led to ADVANCE decisions

| Candidate                                | Decisive Signal                                    | Screener's Words                                                                             |
| ---------------------------------------- | -------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| DeepMind interpretability engineer       | DeepMind + interpretability work                   | "Worked at Deepmind, including doing work on interpretability"                               |
| Engineer with compelling curiosity story | Compelling curiosity/drive story, games connection | "story shows a lot of curiosity and drive, and connection to thinking about games"           |
| Major OSS framework maintainer           | Major OSS maintainer + Softmax enthusiasm          | "Maintainer of a pretty big OSS project -- Big Softmax-specific excitement about AI"         |
| Insider-referred engineer                | Insider referral                                   | "he heard about the job specifically from Adam, which suggests he should know what's up"     |
| CNN/GNN research engineer                | CNN/GNN research background                        | "Background in practical use of CNNs / GNNs"                                                 |
| Apple AI/ML engineer                     | Apple AI/ML + thoughtful alignment philosophy      | "AI / ML experience at Apple -- Application includes interesting thoughts on LLM data risks" |

### Signals that led to REJECT decisions

| Candidate                           | Decisive Signal                                       | Screener's Words                                                                                                                                   |
| ----------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Bootcamp grad / AWS integrator      | Surface-level work                                    | "OSS contributions seem like surface level UI changes, and the building seems like 'putting AWS legos together'"                                   |
| Astrophysicist needing visa         | Unrelated field + visa                                | "background is astrophysics, with no clear connection to the work that we do. Further, they would require visa support"                            |
| Generic backend engineer (no AI)    | Generic background                                    | "Background seems generic (no connection to AI) and not obviously high tier"                                                                       |
| Backend engineer with templated app | Lackluster background, possibly templated application | "lackluster background. Also, the story of 'people wanted to scale horizontally...' has been given by a few other candidates"                      |
| Early-career generic applicant      | Early career, generic app                             | "work experience doesn't seem like a clear translation... nothing Softmax specific (seems like they're copying and pasting)"                       |
| Job-hopping engineer                | Nothing stands out, job hopping                       | "Background doesn't have anything that stands out. Has multiple sub-year jobs"                                                                     |
| Unrelated experience engineer       | Unrelated + generic app                               | "Experience seems lackluster and unrelated to AI. Application is generic and unrelated to Softmax"                                                 |
| Lazy application engineer           | Lazy application                                      | "Application is super lazy -- doesn't demonstrate interest / awareness of what softmax does"                                                       |
| Overconfident self-taught engineer  | Overconfidence without validation                     | "Candidate seems delusionally confident"                                                                                                           |
| AI-adjacent jargon-heavy engineer   | Self-promotional, no hard engineering evidence        | "resume is pretty jargon filled, 'why interested in softmax' is generic... self promotional without clear evidence of them doing hard engineering" |
