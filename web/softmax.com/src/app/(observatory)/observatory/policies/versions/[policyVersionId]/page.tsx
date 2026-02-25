import { Suspense } from "react";

import { Card } from "@observatory/components/Card";
import { CopyableUri } from "@observatory/components/CopyableUri";
import { LinkButton } from "@observatory/components/LinkButton";
import { Spinner } from "@observatory/components/Spinner";
import { UserDisplay } from "@observatory/components/UserDisplay";
import { TasksTable } from "@observatory/EvalTasks/TasksTable";
import { ServerDebugDrain } from "@observatory/lib/debug/ServerDebugDrain";
import { getRepo } from "@observatory/lib/repo/server";
import { policyDashboardRoute, policyRoute } from "@observatory/lib/routes";
import { formatDate } from "@observatory/utils/datetime";
import { formatPolicyVersion } from "@observatory/utils/format";

import { PolicyVersionJobsCard } from "./PolicyVersionJobsCard";
import { PolicyVersionTournamentMembershipsCard } from "./PolicyVersionTournamentMembershipsCard";

export default async function PolicyVersionPage(
  props: PageProps<"/observatory/policies/versions/[policyVersionId]">,
) {
  const { policyVersionId } = await props.params;
  const standaloneDashboardHref = policyDashboardRoute({ policyVersionId });

  const repo = await getRepo();
  const pvInfo = await repo.getPolicyVersion(policyVersionId);

  const policyCreatedAt = pvInfo?.created_at || null;
  const policyDisplay = formatPolicyVersion(pvInfo, policyVersionId);

  return (
    <div className="mx-auto max-w-[1600px] space-y-6 p-6">
      <ServerDebugDrain />
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-foreground-muted text-xs font-semibold tracking-wide uppercase">
            Policy Version
          </p>
          <h1 className="text-foreground text-2xl font-semibold">
            {policyDisplay}
          </h1>
          <div className="text-foreground-muted flex flex-wrap gap-3 text-sm">
            {policyCreatedAt && (
              <span className="text-foreground-muted">
                Created: {formatDate(policyCreatedAt)}
              </span>
            )}
            <span className="text-foreground-muted">
              User: <UserDisplay user={pvInfo.user} userId={pvInfo.user_id} />
            </span>
            <span className="text-foreground-muted flex items-center gap-1">
              Policy Version ID:
              <span className="text-foreground-subtle font-mono text-xs">
                {pvInfo.id}
              </span>
            </span>
          </div>
        </div>
        {pvInfo && (
          <div className="flex gap-2">
            <LinkButton href={standaloneDashboardHref} theme="secondary">
              View Dashboard
            </LinkButton>
            <LinkButton href={policyRoute(pvInfo.policy_id)} theme="tertiary">
              &larr; Back to policy
            </LinkButton>
          </div>
        )}
      </div>

      <CopyableUri uri={`metta://policy/${pvInfo.name}:v${pvInfo.version}`} />

      <Suspense fallback={<Spinner />}>
        <PolicyVersionJobsCard
          policyVersionId={policyVersionId}
          searchParams={props.searchParams}
        />
      </Suspense>

      <Suspense fallback={<Spinner />}>
        <PolicyVersionTournamentMembershipsCard
          policyVersionId={policyVersionId}
        />
      </Suspense>

      <Card title="Tasks">
        <TasksTable initialFilters={{ command: policyVersionId }} hideFilters />
      </Card>
    </div>
  );
}

export async function generateMetadata({
  params,
}: PageProps<"/observatory/policies/versions/[policyVersionId]">) {
  const { policyVersionId } = await params;
  const repo = await getRepo();
  const pvInfo = await repo.getPolicyVersion(policyVersionId);
  const policyDisplay = formatPolicyVersion(pvInfo, policyVersionId);
  return {
    title: `${policyDisplay} | Observatory`,
  };
}
