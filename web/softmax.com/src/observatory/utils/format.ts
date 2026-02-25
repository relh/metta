export type PolicyVersionInfo = {
  name: string;
  version: number;
};

export function formatPolicyVersion(
  policy: PolicyVersionInfo | null | undefined,
  fallback?: string,
): string {
  if (!policy) {
    return fallback ?? "Unknown policy";
  }
  return `${policy.name}:v${policy.version}`;
}
