import { Card } from "@observatory/components/Card";
import { CopyableUri } from "@observatory/components/CopyableUri";
import { StandardPageLayout } from "@observatory/components/layouts/StandardPageLayout";
import { LinkButton } from "@observatory/components/LinkButton";
import { StyledLink } from "@observatory/components/StyledLink";
import {
  Table,
  TableBody,
  TableHeader,
  TD,
  TH,
  TR,
} from "@observatory/components/Table";
import { UserDisplay } from "@observatory/components/UserDisplay";
import { ServerDebugDrain } from "@observatory/lib/debug/ServerDebugDrain";
import { getRepo } from "@observatory/lib/repo/server";
import { policiesRoute, policyVersionRoute } from "@observatory/lib/routes";
import { formatDate, formatRelativeTime } from "@observatory/utils/datetime";

export default async function PolicyPage({
  params,
}: PageProps<"/observatory/policies/[policyId]">) {
  const { policyId } = await params;
  const repo = await getRepo();
  const policyVersionsResponse = await repo.getVersionsForPolicy(policyId, {
    limit: 500,
  });
  const policyVersions = policyVersionsResponse.entries;

  const policyName = policyVersions[0]?.name ?? "Unknown Policy";
  const policyCreatedAt = policyVersions[0]?.policy_created_at ?? null;
  const firstVersion = policyVersions[0];

  return (
    <StandardPageLayout>
      <ServerDebugDrain />
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-foreground-muted text-xs font-semibold tracking-wide uppercase">
            Policy
          </p>
          <h1 className="text-foreground text-2xl font-semibold">
            {policyName}
          </h1>
          <div className="text-foreground-muted flex flex-wrap gap-3 text-sm">
            {firstVersion?.user_id && (
              <span className="text-foreground-muted">
                User:{" "}
                <UserDisplay
                  user={firstVersion.user}
                  userId={firstVersion.user_id}
                />
              </span>
            )}
            {policyCreatedAt && (
              <span
                className="text-foreground-muted"
                title={formatDate(policyCreatedAt)}
              >
                Created: {formatRelativeTime(policyCreatedAt)}
              </span>
            )}
            <span className="text-foreground-muted flex items-center gap-1">
              Policy ID:
              <span className="text-foreground-subtle font-mono text-xs">
                {policyId}
              </span>
            </span>
          </div>
        </div>
        <LinkButton href={policiesRoute()} theme="tertiary">
          ← Back to policies
        </LinkButton>
      </div>

      {policyVersions[0]?.name && (
        <CopyableUri uri={`metta://policy/${policyVersions[0].name}`} />
      )}

      <Card title="Versions">
        {policyVersions.length === 0 ? (
          <div className="text-foreground-muted text-sm">
            No versions found for this policy.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TH>Version</TH>
                <TH>Version ID</TH>
                <TH>Created</TH>
              </TableHeader>
              <TableBody>
                {policyVersions.map((pv) => (
                  <TR key={pv.id}>
                    <TD>
                      <StyledLink
                        href={policyVersionRoute(pv.id)}
                        className="font-medium"
                      >
                        v{pv.version}
                      </StyledLink>
                    </TD>
                    <TD>
                      <span className="text-foreground-muted font-mono text-xs">
                        {pv.id}
                      </span>
                    </TD>
                    <TD title={formatDate(pv.created_at)}>
                      {formatRelativeTime(pv.created_at)}
                    </TD>
                  </TR>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>
    </StandardPageLayout>
  );
}

export async function generateMetadata({
  params,
}: PageProps<"/observatory/policies/[policyId]">) {
  const { policyId } = await params;
  const repo = await getRepo();
  const policyVersionsResponse = await repo.getVersionsForPolicy(policyId, {
    limit: 1,
  });
  const policyVersions = policyVersionsResponse.entries;
  const policyName = policyVersions[0]?.name ?? "Unknown Policy";
  return {
    title: `${policyName} | Observatory`,
  };
}
