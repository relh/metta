# Canary - cogames runner

High level overview:

- Creates a 'good' and 'bad' policy
- Uploads both policies, skipping validation on the 'bad' policy
- Launches a polling process on `cogames submissions --season=test-season`
  - Obtains the `policy_version_id` from the response
  - Starts polling both good and bad jobs for statuses
  - Expects good policy to have only `completed` status
  - Expects bad policy to have only `failed` status

## Run Locally

Ensure local servers are started:

```
metta observatory up
```

Ensure k8s are enabled in your Docker environment and you've ran:

```
metta observatory local-k8s setup
```

In another terminal issue the command:

```
uv run devops/canary/cli.py
```

## Build a test docker image

```
docker build -f devops/canary/Dockerfile.canary_runner -t canary:dev
```

Optional flag `--server prod` to communicate to actual backend (not really needed if dev workflow is setup)

## Run the test image

```
docker run --rm -v $(pwd)/devops/canary/state:/app/devops/canary/state canary:dev
```
