export function formatPolicyDisplay(p: { policy: { id: string; name: string | null; version: number | null } }) {
  if (p.policy.name && p.policy.version !== null) {
    return `${p.policy.name}:v${p.policy.version}`
  }
  return p.policy.id.slice(0, 8)
}
