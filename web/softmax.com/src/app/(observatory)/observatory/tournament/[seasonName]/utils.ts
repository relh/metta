import type { PolicyVersionSummary } from "@observatory/lib/api";

export function formatPolicyTag(policy: PolicyVersionSummary): string {
  if (policy.name && policy.version !== null) {
    return `${policy.name}:v${policy.version}`;
  }
  return policy.id.slice(0, 8);
}

export function formatPolicyDisplay(p: { policy: PolicyVersionSummary }) {
  return formatPolicyTag(p.policy);
}
