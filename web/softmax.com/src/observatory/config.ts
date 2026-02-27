interface Config {
  apiBaseUrl: string;
  authToken?: string;
  policyDashboardUrl: string;
  siteUrl?: string;
}

export const config: Config = {
  apiBaseUrl:
    process.env.OBSERVATORY_API_URL || "http://localhost:3002/api/observatory",
  authToken: process.env.DEV_AUTH_TOKEN, // set in dev mode for convenience based on ~/.metta/config.yaml token
  policyDashboardUrl:
    process.env.OBSERVATORY_POLICY_DASHBOARD_URL || "http://127.0.0.1:5174",
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
