import { z } from "zod";

import { loadUserById } from "./user";

const PolicyVersionSummarySchema = z.object({
  id: z.uuid(),
  name: z.string().nullable(),
  version: z.number().nullable(),
});

export type PolicyVersionSummary = z.infer<typeof PolicyVersionSummarySchema>;

const PoolInfoSchema = z.object({
  name: z.string(),
  description: z.string(),
  config_id: z.string().nullable(),
});

export type PoolInfo = z.infer<typeof PoolInfoSchema>;

const SeasonResponseSchema = z.object({
  name: z.string(),
  summary: z.string(),
  entry_pool: z.string().nullable(),
  leaderboard_pool: z.string().nullable(),
  is_default: z.boolean(),
  pools: z.array(PoolInfoSchema),
});

export type SeasonResponse = z.infer<typeof SeasonResponseSchema>;

const LeaderboardEntrySchema = z.object({
  rank: z.number(),
  policy: PolicyVersionSummarySchema,
  score: z.number(),
  matches: z.number(),
});

export type LeaderboardEntry = z.infer<typeof LeaderboardEntrySchema>;

export type LeaderboardResponse = LeaderboardEntry[];

const PoolMembershipSchema = z.object({
  pool_name: z.string(),
  active: z.boolean(),
  completed: z.number(),
  failed: z.number(),
  pending: z.number(),
});

export type PoolMembership = z.infer<typeof PoolMembershipSchema>;

const PolicySummarySchema = z.object({
  policy: PolicyVersionSummarySchema,
  pools: z.array(PoolMembershipSchema),
  entered_at: z.string(),
});

export type PolicySummary = z.infer<typeof PolicySummarySchema>;

export type PoliciesResponse = PolicySummary[];

const MatchPlayerSummarySchema = z.object({
  policy: PolicyVersionSummarySchema,
  policy_index: z.number(),
  score: z.number().nullable(),
});

const MatchSummarySchema = z.object({
  id: z.uuid(),
  pool_name: z.string(),
  status: z.string(),
  assignments: z.array(z.number()),
  players: z.array(MatchPlayerSummarySchema),
  job_id: z.uuid().nullable(),
  episode_id: z.string().nullable(),
  created_at: z.string(),
});

export type MatchSummary = z.infer<typeof MatchSummarySchema>;

export type MatchesResponse = MatchSummary[];

const MembershipHistoryEntrySchema = z.object({
  season_name: z.string(),
  pool_name: z.string(),
  action: z.string(),
  notes: z.string().nullable(),
  created_at: z.string(),
});

export type MembershipHistoryEntry = z.infer<
  typeof MembershipHistoryEntrySchema
>;

export type MembershipHistoryResponse = MembershipHistoryEntry[];

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

export async function getSeasons(): Promise<SeasonResponse[]> {
  const data = await fetchApi("/tournament/seasons");
  return z.array(SeasonResponseSchema).parse(data);
}

export function findDefaultSeason(
  seasons: SeasonResponse[],
): SeasonResponse | undefined {
  return seasons.find((s) => s.is_default) ?? seasons[0];
}

export async function getLeaderboard(
  seasonName: string,
): Promise<LeaderboardResponse> {
  const data = await fetchApi(
    `/tournament/seasons/${encodeURIComponent(seasonName)}/leaderboard`,
  );
  return z.array(LeaderboardEntrySchema).parse(data);
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
  const url = `/tournament/seasons/${encodeURIComponent(args.seasonName)}/policies${query ? `?${query}` : ""}`;
  const data = await fetchApi(url, args.userId);
  return z.array(PolicySummarySchema).parse(data);
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
  const url = `/tournament/seasons/${encodeURIComponent(seasonName)}/matches${query ? `?${query}` : ""}`;
  const data = await fetchApi(url);
  return z.array(MatchSummarySchema).parse(data);
}

export async function getMyMemberships(
  userId: string,
): Promise<MembershipHistoryResponse> {
  const data = await fetchApi("/tournament/my-memberships", userId);
  return z.array(MembershipHistoryEntrySchema).parse(data);
}

export async function getPolicyMemberships(
  policyVersionId: string,
): Promise<MembershipHistoryResponse> {
  const data = await fetchApi(
    `/tournament/policies/${policyVersionId}/memberships`,
  );
  return z.array(MembershipHistoryEntrySchema).parse(data);
}
