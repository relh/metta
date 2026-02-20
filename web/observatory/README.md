# Observatory

Frontend for https://observatory.softmax-research.net/

## Development

**Frontend only (against prod API):**

```bash
metta observatory frontend --backend [prod|local]
```

Environment variables:

- `OBSERVATORY_API_URL` (default: `http://localhost:8000`)
- `OBSERVATORY_POLICY_DASHBOARD_URL` (default: `http://127.0.0.1:5174`)

## Production

Deployed to EKS via Helm chart at `devops/charts/observatory/`.

- Host: `observatory.softmax-research.net`
- Image built by `.github/workflows/build-observatory-image.yml`
