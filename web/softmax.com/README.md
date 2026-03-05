# Softmax.com

A nextjs app that serves MDX-based static content and dynamic content, including things like auth.

## Development workflow

1. Start local Postgres: `metta dev postgres up -d`
2. Apply DB migrations: `metta dev softmax-com-db-migrate`
3. Start the frontend: `metta dev softmax-com --backend local`
   (or `--backend prod` to point Observatory API calls at production)

The site should be available at `http://localhost:3002`.

### Updating Nextjs pages

These can be modified within `app/`, and updates here should be reflected even quicker.

A page accessible at `https://softmax.com/mypage` will have its definition in `app/mypage/page.tsx`.

In these pages, you are able to import and render MDX from other paths under `src/` by importing those MDX files.

Examples of these types of pages include `src/app/about/page.tsx` and `src/app/page.tsx`.

## Pushing to production

Commits to `main` will trigger a github action.

The github action pushes a docker image (the same as the one you are running locally in your development workflow) to softmax ECR.

EKS (AWS Kubernetes) picks up this image and deploys it.

Cloudflare sits in front of this. Cache-control headers sent back from the nextjs app control Cloudflare caching behavior.

## Preview branches

Each open PR gets deployed to a preview branch.

## API Endpoints

### Authentication

- `GET/POST /api/auth/*` - NextAuth.js endpoints
- `GET /api/auth/signin` - Sign in page
- `GET /api/auth/signout` - Sign out

### User Management

- `GET /api/user` - Get current user information
- `GET /api/validate` - Validate current session
- `POST /api/validate` - Validate session token (for other services)

### Health Check

- `GET /api/health` - Service health and database connectivity

## Usage in Other Services

Other services can validate sessions by calling:

```typescript
// Validate current session
const response = await fetch("http://localhost:3002/api/validate");
const { valid, user } = await response.json();

// Validate specific session token
const response = await fetch("http://localhost:3002/api/validate", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ sessionToken: "token-here" }),
});
```
