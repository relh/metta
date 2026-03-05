import type { JobRequest, PolicyVersionRow } from "@observatory/lib/repo";
import type { Repo } from "@observatory/lib/repo";

const PAGE_SIZE = 500;

type BardoPolicy = {
  policyId: string;
  policyVersionId: string;
  name: string;
  userId: string;
  userName: string;
  createdAt: string;
  activeJobIds: string[];
};

type BardoActiveJob = {
  id: string;
  status: JobRequest["status"];
  policyVersionIds: string[];
};

export type BardoWorldState = {
  generatedAt: string;
  policies: BardoPolicy[];
  activeJobs: BardoActiveJob[];
};

type PolicySummaryRow = {
  id: string;
  name: string;
  user_id: string;
  created_at: string;
  user?: {
    name?: string | null;
  } | null;
};

async function fetchAllPolicies(
  repo: Repo,
  nameFilter?: string,
): Promise<PolicySummaryRow[]> {
  const entries: PolicySummaryRow[] = [];

  for (let offset = 0; ; offset += PAGE_SIZE) {
    const response = await repo.getPolicies({
      limit: PAGE_SIZE,
      offset,
      name_fuzzy: nameFilter?.trim() || undefined,
    });
    entries.push(...response.entries);
    if (response.entries.length < PAGE_SIZE) break;
  }

  return entries;
}

function selectLatestPolicyVersions(
  policyVersions: PolicyVersionRow[],
  policyIds: Set<string>,
): Map<string, PolicyVersionRow> {
  const latestByPolicyId = new Map<string, PolicyVersionRow>();

  for (const policyVersion of policyVersions) {
    if (!policyIds.has(policyVersion.policy_id)) continue;
    if (latestByPolicyId.has(policyVersion.policy_id)) continue;
    latestByPolicyId.set(policyVersion.policy_id, policyVersion);
    if (latestByPolicyId.size >= policyIds.size) break;
  }

  return latestByPolicyId;
}

async function fetchLatestPolicyVersionsForPolicies(
  repo: Repo,
  policyIds: Set<string>,
): Promise<Map<string, PolicyVersionRow>> {
  const latestByPolicyId = new Map<string, PolicyVersionRow>();

  for (let offset = 0; ; offset += PAGE_SIZE) {
    const response = await repo.getPolicyVersions({
      limit: PAGE_SIZE,
      offset,
    });

    const pageLatest = selectLatestPolicyVersions(response.entries, policyIds);
    for (const [policyId, latestVersion] of pageLatest) {
      if (latestByPolicyId.has(policyId)) continue;
      latestByPolicyId.set(policyId, latestVersion);
    }

    if (latestByPolicyId.size >= policyIds.size) break;
    if (response.entries.length < PAGE_SIZE) break;
  }

  return latestByPolicyId;
}

function normalizeActiveJobs(jobs: JobRequest[]): BardoActiveJob[] {
  const normalized: BardoActiveJob[] = [];

  for (const job of jobs) {
    const jobId = String(job.id ?? "").trim();
    if (!jobId) continue;

    const policyVersionIds = (job.policy_versions ?? [])
      .map((summary) => String(summary.policy?.id ?? "").trim())
      .filter((value) => value.length > 0);

    normalized.push({
      id: jobId,
      status: job.status,
      policyVersionIds,
    });
  }

  return normalized;
}

function collectActiveJobPolicyVersionUsage(
  jobs: BardoActiveJob[],
): Map<string, Set<string>> {
  const activeByPolicyVersionId = new Map<string, Set<string>>();

  for (const job of jobs) {
    for (const policyVersionId of job.policyVersionIds) {
      const current = activeByPolicyVersionId.get(policyVersionId);
      if (current) {
        current.add(job.id);
      } else {
        activeByPolicyVersionId.set(policyVersionId, new Set([job.id]));
      }
    }
  }

  return activeByPolicyVersionId;
}

function resolveUserName(
  policy: PolicySummaryRow,
  latestVersion: PolicyVersionRow,
): string {
  const policyUserName = policy.user?.name?.trim();
  if (policyUserName) return policyUserName;

  const latestVersionUserName = latestVersion.user?.name?.trim();
  if (latestVersionUserName) return latestVersionUserName;

  return policy.user_id;
}

async function fetchActiveEpisodeJobs(repo: Repo): Promise<JobRequest[]> {
  try {
    const user = await repo.whoami();
    if (!user.is_softmax_team_member) return [];
  } catch {
    return [];
  }

  const jobs: JobRequest[] = [];
  for (let offset = 0; ; offset += PAGE_SIZE) {
    const page = await repo.getJobs({
      job_type: "episode",
      statuses: ["pending", "dispatched", "running"],
      limit: PAGE_SIZE,
      offset,
    });
    jobs.push(...page);
    if (page.length < PAGE_SIZE) break;
  }

  return jobs;
}

export async function loadBardoWorldState(args: {
  repo: Repo;
  nameFilter?: string;
}): Promise<BardoWorldState> {
  const [policies, activeJobsRaw] = await Promise.all([
    fetchAllPolicies(args.repo, args.nameFilter),
    fetchActiveEpisodeJobs(args.repo),
  ]);

  const latestByPolicyId = await fetchLatestPolicyVersionsForPolicies(
    args.repo,
    new Set(policies.map((policy) => policy.id)),
  );
  const activeJobs = normalizeActiveJobs(activeJobsRaw);
  const activeByPolicyVersionId =
    collectActiveJobPolicyVersionUsage(activeJobs);

  const rows: BardoPolicy[] = [];
  for (const policy of policies) {
    const latestVersion = latestByPolicyId.get(policy.id);
    if (!latestVersion) continue;

    const activeJobIds = [
      ...(activeByPolicyVersionId.get(latestVersion.id) ?? new Set<string>()),
    ].sort();

    rows.push({
      policyId: policy.id,
      policyVersionId: latestVersion.id,
      name: policy.name,
      userId: policy.user_id,
      userName: resolveUserName(policy, latestVersion),
      createdAt: latestVersion.created_at,
      activeJobIds,
    });
  }

  rows.sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));

  return {
    generatedAt: new Date().toISOString(),
    policies: rows,
    activeJobs,
  };
}
