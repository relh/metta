import {
  AccessDenied,
  SoftmaxAdminGuard,
} from "@observatory/components/SoftmaxGuard";
import { Card } from "@observatory/components/Card";
import { LinkButton } from "@observatory/components/LinkButton";
import { StandardPageLayout } from "@observatory/components/layouts/StandardPageLayout";
import { StyledLink } from "@observatory/components/StyledLink";
import {
  Table,
  TableBody,
  TableHeader,
  TD,
  TH,
  TR,
} from "@observatory/components/Table";
import { ServerDebugDrain } from "@observatory/lib/debug/ServerDebugDrain";
import type { AdminUserSubmittedPolicy } from "@observatory/lib/repo";
import { getRepo } from "@observatory/lib/repo/server";
import { adminUsersRoute, policyRoute } from "@observatory/lib/routes";
import { formatDate, formatRelativeTime } from "@observatory/utils/datetime";

import { AdminUserRoles } from "../AdminUserRoles";

function displayName(
  name: string | null,
  email: string | null,
  userId: string,
) {
  return name?.trim() || email?.trim() || userId;
}

function formatSummaryValue(value: string | null): string {
  return value ? formatDate(value) : "—";
}

function uniqueSeasonCount(
  submittedPolicies: AdminUserSubmittedPolicy[],
): number {
  return new Set(
    submittedPolicies.flatMap((policy) =>
      policy.seasons.map(
        (season) => `${season.season_name}:v${season.season_version}`,
      ),
    ),
  ).size;
}

export default async function AdminUserPage({
  params,
}: {
  params: Promise<{ userId: string }>;
}) {
  const { userId } = await params;
  const repo = await getRepo();
  const userInfo = await repo.whoami();
  if (!userInfo.is_softmax_admin) {
    return (
      <AccessDenied message="This page is only available to Softmax admins." />
    );
  }

  const { user, submitted_policies: submittedPolicies } =
    await repo.getAdminUser(userId);
  const seasonCount = uniqueSeasonCount(submittedPolicies);
  const title = displayName(user.name, user.email, user.id);

  return (
    <SoftmaxAdminGuard>
      <StandardPageLayout>
        <ServerDebugDrain />
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <p className="text-foreground-muted text-xs font-semibold tracking-wide uppercase">
              User
            </p>
            <h1>{title}</h1>
            <div className="text-foreground-muted flex flex-wrap gap-3 text-sm">
              {user.email && <span>{user.email}</span>}
              <span>{submittedPolicies.length} submitted policies</span>
              <span>{seasonCount} seasons</span>
            </div>
          </div>
          <LinkButton href={adminUsersRoute()} theme="tertiary">
            ← Back to users
          </LinkButton>
        </div>

        <Card padding="md">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="space-y-1">
              <p className="text-foreground-muted text-xs font-semibold tracking-wide uppercase">
                User ID
              </p>
              <p className="text-foreground font-mono text-sm break-all">
                {user.id}
              </p>
            </div>
            <div className="space-y-1">
              <p className="text-foreground-muted text-xs font-semibold tracking-wide uppercase">
                Roles
              </p>
              <AdminUserRoles
                isSoftmaxTeamMember={user.is_softmax_team_member}
                isSoftmaxAdmin={user.is_softmax_admin}
                className="text-sm"
              />
            </div>
            <div className="space-y-1">
              <p className="text-foreground-muted text-xs font-semibold tracking-wide uppercase">
                Signup Date
              </p>
              <p className="text-foreground text-sm">
                {formatSummaryValue(user.created_at)}
              </p>
            </div>
            <div className="space-y-1">
              <p className="text-foreground-muted text-xs font-semibold tracking-wide uppercase">
                First Upload
              </p>
              <p className="text-foreground text-sm">
                {formatSummaryValue(user.first_policy_upload_at)}
              </p>
            </div>
            <div className="space-y-1">
              <p className="text-foreground-muted text-xs font-semibold tracking-wide uppercase">
                Last Upload
              </p>
              <p className="text-foreground text-sm">
                {formatSummaryValue(user.last_policy_upload_at)}
              </p>
            </div>
            <div className="space-y-1">
              <p className="text-foreground-muted text-xs font-semibold tracking-wide uppercase">
                First Tournament Submission
              </p>
              <p className="text-foreground text-sm">
                {formatSummaryValue(user.first_tournament_submission_at)}
              </p>
            </div>
            <div className="space-y-1">
              <p className="text-foreground-muted text-xs font-semibold tracking-wide uppercase">
                Last Tournament Submission
              </p>
              <p className="text-foreground text-sm">
                {formatSummaryValue(user.last_tournament_submission_at)}
              </p>
            </div>
          </div>
        </Card>

        <Card title="Submitted Policies">
          {submittedPolicies.length === 0 ? (
            <div className="text-foreground-muted text-sm">
              No tournament submissions found for this user.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TH>Policy</TH>
                  <TH>Versions</TH>
                  <TH>Created</TH>
                  <TH>Seasons</TH>
                </TableHeader>
                <TableBody>
                  {submittedPolicies.map((policy) => (
                    <TR key={policy.id}>
                      <TD>
                        <StyledLink
                          href={policyRoute(policy.id)}
                          className="font-medium"
                        >
                          {policy.name}
                        </StyledLink>
                      </TD>
                      <TD>
                        {policy.version_count} version
                        {policy.version_count === 1 ? "" : "s"}
                      </TD>
                      <TD title={formatDate(policy.created_at)}>
                        {formatRelativeTime(policy.created_at)}
                      </TD>
                      <TD>
                        <div className="space-y-1">
                          {policy.seasons.map((season) => (
                            <div
                              key={`${policy.id}-${season.season_name}-v${season.season_version}`}
                              title={`Submitted ${formatDate(season.submitted_at)}`}
                              className="text-sm"
                            >
                              {season.season_name}:v{season.season_version}
                            </div>
                          ))}
                        </div>
                      </TD>
                    </TR>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </Card>
      </StandardPageLayout>
    </SoftmaxAdminGuard>
  );
}
