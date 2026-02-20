import type {
  LeaderboardEntry,
  MatchResponse,
  MembershipHistoryEntry,
  PolicySummary,
  SeasonDetail,
  SeasonSummary,
  SeasonVersionInfo,
} from "@/lib/api";

import { loadUserById } from "./user";

export type {
  LeaderboardEntry,
  MatchResponse,
  MembershipHistoryEntry,
  PolicySummary,
  SeasonDetail,
  SeasonSummary,
  SeasonVersionInfo,
} from "@/lib/api";
export type { PoolMembership, PolicyVersionSummary } from "@/lib/api";

export type LeaderboardResponse = LeaderboardEntry[];
export type PoliciesResponse = PolicySummary[];
export type MatchesResponse = MatchResponse[];
export type MembershipHistoryResponse = MembershipHistoryEntry[];

const decodePathSegment = (value: string) => {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
};

const encodePathSegment = (value: string) =>
  encodeURIComponent(decodePathSegment(value));

async function fetchApi(url: string, userId?: string): Promise<unknown> {
  let headers: Record<string, string> = {};
  if (userId) {
    const user = await loadUserById(userId);
    if (!user) {
      throw new Error(`User not found: ${userId}`);
    }
    headers = {
      "X-User-Id": userId,
      "X-User-Email": user.email ?? "",
      "X-User-Is-Softmax-Team-Member": user.isSoftmaxTeamMember
        ? "true"
        : "false",
      "X-Auth-Secret": process.env.OBSERVATORY_AUTH_SECRET ?? "",
    };
  }

  const response = await fetch(`${process.env.OBSERVATORY_API_URL}${url}`, {
    redirect: "follow",
    headers,
    next: { revalidate: 60 },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      if (data.detail) {
        detail = String(data.detail);
      }
    } catch {}
    throw new Error(`Failed to fetch ${url}: ${detail}`);
  }
  return response.json();
}

export async function getSeasons(): Promise<SeasonSummary[]> {
  return (await fetchApi("/tournament/seasons")) as SeasonSummary[];
}

export async function getSeason(seasonName: string): Promise<SeasonDetail> {
  return (await fetchApi(
    `/tournament/seasons/${encodePathSegment(seasonName)}`,
  )) as SeasonDetail;
}

export function findDefaultSeason(
  seasons: SeasonSummary[],
): SeasonSummary | undefined {
  return seasons.find((s) => s.is_default) ?? seasons[0];
}

export async function getLeaderboard(
  seasonName: string,
): Promise<LeaderboardResponse> {
  return (await fetchApi(
    `/tournament/seasons/${encodePathSegment(seasonName)}/leaderboard`,
  )) as LeaderboardResponse;
}

export async function getPolicies(
  args: {
    seasonName: string;
  } & (
    | { userId: string; mine: boolean }
    | { userId?: undefined; mine?: undefined | false }
  ),
): Promise<PoliciesResponse> {
  const params = new URLSearchParams();
  if (args.mine) params.set("mine", "true");
  const query = params.toString();
  const url = `/tournament/seasons/${encodePathSegment(args.seasonName)}/policies${query ? `?${query}` : ""}`;
  return (await fetchApi(url, args.userId)) as PoliciesResponse;
}

export async function getMatches(
  seasonName: string,
  options: {
    limit?: number;
    offset?: number;
    poolNames?: string[];
    policyVersionIds?: string[];
  } = {},
): Promise<MatchesResponse> {
  const params = new URLSearchParams();
  if (options.limit) params.set("limit", String(options.limit));
  if (options.offset) params.set("offset", String(options.offset));
  if (options.poolNames) {
    for (const name of options.poolNames) {
      params.append("pool_names", name);
    }
  }
  if (options.policyVersionIds) {
    for (const id of options.policyVersionIds) {
      params.append("policy_version_ids", id);
    }
  }
  const query = params.toString();
  const url = `/tournament/seasons/${encodePathSegment(seasonName)}/matches${query ? `?${query}` : ""}`;
  return (await fetchApi(url)) as MatchesResponse;
}

export async function getSeasonVersions(
  seasonName: string,
): Promise<SeasonVersionInfo[]> {
  return (await fetchApi(
    `/tournament/seasons/${encodePathSegment(seasonName)}/versions`,
  )) as SeasonVersionInfo[];
}

export async function getMyMemberships(
  userId: string,
): Promise<MembershipHistoryResponse> {
  return (await fetchApi(
    "/tournament/my-memberships",
    userId,
  )) as MembershipHistoryResponse;
}

export async function getPolicyMemberships(
  policyVersionId: string,
): Promise<MembershipHistoryResponse> {
  return (await fetchApi(
    `/tournament/policies/${policyVersionId}/memberships`,
  )) as MembershipHistoryResponse;
}
