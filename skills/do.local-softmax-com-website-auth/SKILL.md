---
name: do.local-softmax-com-website-auth
description:
  Use when starting/restarting local softmax.com website instances with correct auth env vars (NEXTAUTH_URL, GitHub OAuth,
  DB URL), and when fixing missing GitHubTeamMember rows so internal pages show up.
---

# Local Softmax.com Website Auth

Use this when launching `web/softmax.com` on a requested local port with proper auth wiring.

**Announce at start:** "Checking ngrok mapping and auth env vars, then starting the local softmax.com server on the requested port."

## Steps

1. Resolve `NEXTAUTH_URL` from ngrok config and set GitHub callback URL.

```bash
ROOT=/workspace/metta-<N>
PORT=30<N>
APP_NAME="app${PORT}"
NGROK_CONFIG=~/.config/ngrok/ngrok.yml

NEXTAUTH_DOMAIN=$(
  awk -v app="$APP_NAME" '
    $0 ~ "^  " app ":" {in_app=1; next}
    in_app && $0 ~ "^    domain:" {print $2; exit}
    in_app && $0 !~ "^    " {in_app=0}
  ' "$NGROK_CONFIG"
)

if [ -n "$NEXTAUTH_DOMAIN" ]; then
  NEXTAUTH_URL="https://${NEXTAUTH_DOMAIN}"
else
  NEXTAUTH_URL="http://127.0.0.1:${PORT}"
fi

GITHUB_CALLBACK_URL="${NEXTAUTH_URL}/api/auth/callback/github"
echo "$GITHUB_CALLBACK_URL"
```

GitHub app install/settings link:  
`https://github.com/organizations/Metta-AI/settings/installations/103285963`

Ensure the Softmax GitHub app/oauth config includes callback URL(s) like:  
`https://metta-3010-1772825529-16965.ngrok-free.app/api/auth/callback/github`

2. Start/restart the local server in tmux (no secrets in files; pass at runtime).

```bash
PNPM=/home/ubuntu/.nvm/versions/node/v25.6.1/bin/pnpm
DATABASE_URL='postgres://postgres:password@127.0.0.1:5433/softmax_com'
OBSERVATORY_API_URL='https://api.observatory.softmax-research.net'

# Optionally fetch GitHub OAuth vars from AWS Secrets Manager:
aws secretsmanager get-secret-value \
  --secret-id github/oauth-dev \
  --query SecretString \
  --output text | jq -r .

# Example: export vars from that secret payload
# (do not store raw secrets in repo files)
eval "$(aws secretsmanager get-secret-value \
  --secret-id github/oauth-dev \
  --query SecretString \
  --output text \
  | jq -r '"export GITHUB_CLIENT_ID=\(.GITHUB_CLIENT_ID)\\nexport GITHUB_CLIENT_SECRET=\(.GITHUB_CLIENT_SECRET)"')"

tmux kill-session -t "softmax-${PORT}" 2>/dev/null || true
fuser -k "${PORT}"/tcp 2>/dev/null || true
rm -rf "${ROOT}/web/softmax.com/.next"

tmux new-session -d -s "softmax-${PORT}" \
  "cd ${ROOT}/web/softmax.com && \
   DEV_AUTH_DISABLE_HACK='1' \
   NEXTAUTH_URL='${NEXTAUTH_URL}' \
   NEXTAUTH_SECRET='dev-nextauth-secret' \
   DATABASE_URL='${DATABASE_URL}' \
   OBSERVATORY_API_URL='${OBSERVATORY_API_URL}' \
   GITHUB_CLIENT_ID='${GITHUB_CLIENT_ID}' \
   GITHUB_CLIENT_SECRET='${GITHUB_CLIENT_SECRET}' \
   ${PNPM} exec next dev -p ${PORT}"
```

3. Verify wiring.

```bash
curl -fsS "http://127.0.0.1:${PORT}/api/health"
curl -fsS "http://127.0.0.1:${PORT}/api/auth/providers"
ss -ltnp | rg ":${PORT}\\b"
```

Confirm `providers` includes `github` and uses the expected `NEXTAUTH_URL`.

`providers` should include `github` and use the same `NEXTAUTH_URL` domain.

4. If sign-in works but internal pages still do not appear, fix `GitHubTeamMember` rows.

If internal-only pages still do not appear, upsert `GitHubTeamMember`.

Find local website user and GitHub account id:

```bash
docker exec <postgres-container> psql -U postgres -d <website-db> -c \
  'select u.id, u.email, a.provider, a."providerAccountId" from "User" u left join "Account" a on a."userId" = u.id order by u.email, a.provider;'
```

Optional: resolve GitHub login from numeric id:

```bash
curl -fsSL https://api.github.com/user/<github-id> | jq -r '.login'
```

Upsert matching `GitHubTeamMember` row:

```bash
docker exec <postgres-container> psql -U postgres -d <website-db> -c \
  "insert into \"GitHubTeamMember\" (\"userId\", \"login\") values ('<github-id>', '<login>')
   on conflict (\"userId\") do update set \"login\" = excluded.\"login\";"
```

Verify website now treats user as internal:

```bash
docker exec <postgres-container> psql -U postgres -d <website-db> -c \
  "select u.email,
          exists(select 1 from \"GitHubTeamMember\" g
                 where g.\"userId\" in (
                   select a.\"providerAccountId\" from \"Account\" a
                   where a.\"userId\" = u.id and a.provider = 'github'
                 )) as is_softmax_team_member
   from \"User\" u
   order by u.email;"
```

Refresh the page. If the nav still looks stale, sign out and sign back in once.

Refresh; if still stale, sign out and sign in again.

## Integration

**Pairs with:**

- `db.run-and-triage` if auth/provider wiring is correct but role gating still fails.
