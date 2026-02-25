export const FOCUS_POLICY_QUERY_KEY = "focus_policy";

export function parseFocusedPolicyIds(
  raw: string | null | undefined,
): string[] {
  if (!raw) {
    return [];
  }

  const seen = new Set<string>();
  const ids: string[] = [];
  for (const token of raw.split(",")) {
    const id = token.trim();
    if (!id || seen.has(id)) {
      continue;
    }
    seen.add(id);
    ids.push(id);
  }
  return ids;
}

export function withFocusedPolicyIds(
  searchParams: URLSearchParams,
  policyIds: string[],
): URLSearchParams {
  const next = new URLSearchParams(searchParams.toString());
  if (policyIds.length > 0) {
    next.set(FOCUS_POLICY_QUERY_KEY, policyIds.join(","));
  } else {
    next.delete(FOCUS_POLICY_QUERY_KEY);
  }
  return next;
}
