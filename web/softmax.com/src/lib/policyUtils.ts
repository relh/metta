export function formatPolicyLabel(policy: {
  id: string;
  name: string | null;
  version: number | null;
}): string {
  if (policy.name && policy.version !== null) {
    return `${policy.name}:v${policy.version}`;
  }
  return policy.id.slice(0, 8);
}
