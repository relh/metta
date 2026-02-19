---
name: do.kiosk-update
description:
  Use when updating a Softmax kiosk/TV display over SSH; covers the base login/update/restart flow, single-page Firefox
  kiosk mode, split top/bottom mode, and resolving Datadog dashboard names into public share URLs.
---

# Kiosk Update

## Overview

Use this when a user asks to change what a kiosk/TV displays. First run the base SSH/edit/restart workflow, then apply
the specific mode (single page or split), and optionally resolve Datadog dashboard names to share links.

**Announce at start:** "I will log into the kiosk host, update `~/startup.bash` (and split HTML if needed), restart
Firefox, and report what is now displayed."

## Step 1: Base workflow (always)

1. Treat `kiosk` and `tv` as synonyms.
2. Map display number:
   - `0` -> host `softmax-display-0000`, password `softmax_0000`
   - `1` -> host `softmax-display-0001`, password `softmax_0001`
3. SSH in (password auth) and inspect current files:

```bash
ssh softmax@softmax-display-0000
nl -ba ~/startup.bash
[ -f ~/kiosk-split.html ] && nl -ba ~/kiosk-split.html | sed -n '1,80p'
```

4. Update files for the requested mode.
5. Apply immediately by restarting from startup script:

```bash
bash ~/startup.bash
sleep 2
pgrep -fa 'firefox.*kiosk' || true
```

6. Report that restart was performed and what now appears on screen.

Note: users may say `startup.sh`, but this host currently uses `~/startup.bash`.

## Step 2: Single webpage mode

Use when user wants one page fullscreen.

`~/startup.bash` pattern:

```bash
#!/bin/bash
set -euo pipefail

url="https://example.com/"
for pid in $(pgrep firefox || true); do
  kill -9 "$pid"
done

DISPLAY=:0 firefox --kiosk --new-tab "$url" &
```

## Step 3: Split top/bottom mode

Use when user wants two pages, top and bottom halves.

`~/startup.bash` pattern:

```bash
#!/bin/bash
set -euo pipefail

HTML_PATH="/home/softmax/kiosk-split.html"
for pid in $(pgrep firefox || true); do
  kill -9 "$pid"
done

DISPLAY=:0 firefox --kiosk "file://$HTML_PATH" &
```

`~/kiosk-split.html` pattern: two iframes, each `height: 50vh`, top first then bottom.

If user says "side by side" and does not clarify orientation, confirm whether they mean top/bottom or left/right before
editing.

## Step 4: Datadog dashboard name -> public URL

Use this when user gives dashboard names instead of URLs.

1. Find candidates:

```bash
uv run python devops/datadog/cli.py dashboards list -t "System Health"
uv run python devops/datadog/cli.py dashboards list -t "Skills"
```

2. If multiple matches, show IDs/titles and confirm exact dashboard with the user.

3. Create a public share link (`https://p.datadoghq.com/sb/...`) for each selected dashboard ID:

```bash
DASHBOARD_ID="h3w-ibt-gkv"
uv run python - <<'PY'
import os
from datadog_api_client import ApiClient
from datadog_api_client.v1.api.dashboards_api import DashboardsApi
from datadog_api_client.v1.model.dashboard_share_type import DashboardShareType
from datadog_api_client.v1.model.dashboard_type import DashboardType
from datadog_api_client.v1.model.shared_dashboard import SharedDashboard
from devops.datadog.dashboards_client import DatadogDashboardsClient

conf = DatadogDashboardsClient()._build_configuration()
with ApiClient(conf) as client:
    api = DashboardsApi(client)
    shared = api.create_public_dashboard(
        body=SharedDashboard(
            dashboard_id=os.environ["DASHBOARD_ID"],
            dashboard_type=DashboardType.CUSTOM_TIMEBOARD,
            share_type=DashboardShareType.OPEN,
        )
    )
    print(shared.public_url)
PY
```

4. Use those URLs as top/bottom values in split mode.

## Integration

**Pairs with:**

- `do.datadog-api-auth` when Datadog API credentials are missing.
