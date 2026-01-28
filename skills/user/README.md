# User skills

Use this folder for clearly user-specific skills or templates that should live alongside the shared `skills/` registry
without becoming global defaults.

Layout

- `skills/user/<username>/` for user-specific skill material.
- If a skill is broadly useful, place it in `skills/` instead of here so everyone loads it by default.
- If you add skills in this area, keep the same `SKILL.md` format as global skills and use a unique skill name (consider
  prefixing with your username, e.g. `relh:my-skill`).
- Add a `.private` file in the skill directory to exclude it from bulk sync scripts.
