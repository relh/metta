interface Config {
  apiBaseUrl: string;
  authToken?: string;
  policyDashboardUrl: string | null;
  diagnoseUrl: string | null;
  trainBoardUrl: string | null;
  chatpropUrl: string | null;
  bardoUrl: string | null;
  siteUrl?: string;
}

function resolveFragileServiceUrl(
  configuredUrl: string | undefined,
  localDevDefault?: string,
): string | null {
  const trimmed = configuredUrl?.trim();
  if (trimmed) return trimmed;
  if (process.env.NODE_ENV === "production") return null;
  return localDevDefault ?? null;
}

export const config: Config = {
  apiBaseUrl:
    process.env.OBSERVATORY_API_URL || "http://localhost:3002/api/observatory",
  authToken: process.env.DEV_AUTH_TOKEN, // set in dev mode for convenience based on ~/.metta/config.yaml token
  policyDashboardUrl: resolveFragileServiceUrl(
    process.env.OBSERVATORY_POLICY_DASHBOARD_URL,
    "http://127.0.0.1:5174",
  ),
  diagnoseUrl: resolveFragileServiceUrl(
    process.env.OBSERVATORY_DIAGNOSE_URL,
    "http://127.0.0.1:5174/diagnose",
  ),
  trainBoardUrl: resolveFragileServiceUrl(
    process.env.OBSERVATORY_TRAIN_BOARD_URL,
    "http://127.0.0.1:8877",
  ),
  chatpropUrl: resolveFragileServiceUrl(
    process.env.OBSERVATORY_CHATPROP_URL,
    "http://127.0.0.1:8765",
  ),
  bardoUrl: resolveFragileServiceUrl(
    process.env.OBSERVATORY_BARDO_URL,
    "http://127.0.0.1:5174/bardo",
  ),
  siteUrl: process.env.SITE_URL,
};

/** True when running locally */
export function isDevMode(): boolean {
  const localhosts = ["localhost", "127.0.0.1"];
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    return localhosts.includes(h);
  }
  if (!config.siteUrl) {
    return false;
  }
  return localhosts.includes(new URL(config.siteUrl).hostname);
}
