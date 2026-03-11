# Softmax play.md

Use this prompt if you are an AI coding agent helping a human start playing in the Alignment League.

## Goal

Get a policy onto the Alignment League leaderboard without relying on the browser tutorial.

## Workflow

1. Clone `https://github.com/Metta-AI/cogames.git` and work from that checkout.
2. Read `README.md` for the overall flow. Focus on quick start, auth, upload, submissions, and season commands.
   Skip `cogames tutorial play` unless the human explicitly asks for the GUI tutorial.
3. Use Python 3.12. Create an isolated environment and install `cogames`.
   The install is large and may take a few minutes.

   ```bash
   uv venv .venv --python 3.12
   source .venv/bin/activate
   uv pip install cogames
   ```

   If `uv` is unavailable, use `python -m venv .venv` and `pip install cogames`, but still ensure Python 3.12.

4. After install, prefer live CLI help over stale examples in docs or prompts.

   ```bash
   cogames --help
   cogames pickup --help
   cogames season --help
   cogames upload --help
   ```

5. Run a headless sanity check so the agent is actually playing matches.

   ```bash
   cogames pickup --policy starter --pool random --episodes 1 --steps 300
   ```

6. Inspect seasons and choose an explicit in-progress freeplay season.
   Do not rely on hardcoded old examples.

   ```bash
   cogames season list
   cogames season show <SEASON>
   ```

7. Authenticate with Softmax. Use a longer auth window.

   ```bash
   cogames login --timeout 600
   ```

8. If the browser and CLI are on different machines or sessions, the localhost callback may fail.
   In that case, finish sign-in until the browser lands on a URL like `http://127.0.0.1:<port>/callback?token=...`, copy the token value, and save it manually:

   ```bash
   cogames auth set-token '<TOKEN>'
   cogames auth status
   ```

9. Upload a starter policy to the chosen season.

   ```bash
   cogames upload --policy "class=cogames.policy.starter_agent.StarterPolicy" --name "$USER.play-md-starter-policy" --season <SEASON> --skip-validation
   ```

10. Confirm the submission.

```bash
cogames submissions --season <SEASON> --policy "$USER.play-md-starter-policy"
cogames leaderboard --season <SEASON>
```

## Troubleshooting

- If `README.md` and live CLI help disagree, follow live CLI help.
- If `cogames login` hangs in a remote environment, use the manual token flow above.
- If `cogames` fails at import time with a `pufferlib` / Torch / CUDA native-extension error, rebuild `pufferlib-core` against the current environment before continuing.
- Prefer explicit `--season` selection over server defaults.

## Operating rules

- Keep steps observable and report command output briefly.
- Ask the human before browser-mediated auth, uploads, or any consent action.
- Do not paste auth tokens into shared logs if avoidable.
- Once the starter policy works, iterate with `cogames diagnose` and `cogames pickup`.
