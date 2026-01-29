# Skill Namespaces

This repo uses dot-separated namespaces for skill names (e.g., `pr.fix-ci`).

## Prefix map

| Prefix  | Domain / Intent                                      | Examples                            |
| ------- | ---------------------------------------------------- | ----------------------------------- |
| `pr.`   | PR/Graphite/GitHub workflow                          | pr.fix-ci, pr.summary               |
| `st.`   | Stack management (Graphite stacks)                   | st.make-stack, st.split             |
| `tr.`   | Training / run orchestration                         | tr.cogames-command                  |
| `db.`   | Debugging / triage                                   | db.fix-traceback                    |
| `do.`   | DevOps / infra / ops                                 | do.mettabox-ops, do.worktrunk       |
| `cb.`   | Codebase analysis/refactor/cleanup                   | cb.review-main, cb.cleanup-refactor |
| `sk.`   | Skill management (create/update/submit/sync skills)  | sk.make-skill, sk.submit-skill      |
| `t.`    | Testing                                              | t.run-tests                         |
| `r.`    | Repo scaffolding / package creation                  | r.make-package                      |
| `cf.`   | Control-flow / meta-execution                        | cf.really                           |
| `n.`    | Nishad-specific variants (only when truly personal)  | n.debug-jobs                        |
| `relh.` | Richard-specific variants (only when truly personal) | relh.cb.branch-hygiene              |

## Rules

- Prefer the shared prefixes above; only use `n.`/`relh.` for clearly personal skills.
- If a skill touches multiple domains, pick the most central intent.
- If no prefix fits, propose a new prefix in this file before adding the skill.

## When creating a new skill

- Always read this file first and select the namespace from the table.
- Use the chosen prefix in the directory name and the `name:` field in `SKILL.md`.
