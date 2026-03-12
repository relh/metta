import {
  AccessDenied,
  SoftmaxAdminGuard,
} from "@observatory/components/SoftmaxGuard";
import { Card } from "@observatory/components/Card";
import {
  Table,
  TableBody,
  TableHeader,
  TD,
  TH,
  TR,
} from "@observatory/components/Table";
import { StandardPageLayout } from "@observatory/components/layouts/StandardPageLayout";
import { ServerDebugDrain } from "@observatory/lib/debug/ServerDebugDrain";
import { getRepo } from "@observatory/lib/repo/server";
import { formatDate } from "@observatory/utils/datetime";

function formatUploadDate(value: string | null | undefined): string {
  return value ? formatDate(value) : "Never";
}

export default async function AdminUsersPage() {
  const repo = await getRepo();
  const userInfo = await repo.whoami();
  if (!userInfo.is_softmax_admin) {
    return (
      <AccessDenied message="This page is only available to Softmax admins." />
    );
  }

  const report = await repo.getAdminUsersReport();

  return (
    <SoftmaxAdminGuard>
      <StandardPageLayout>
        <div className="space-y-2">
          <h1>Admin Users</h1>
          <p className="text-foreground-muted max-w-4xl text-balance">
            All signed-up users, joined with their first and most recent policy
            upload timestamps from Observatory.
          </p>
        </div>
        <Card padding="md">
          <div className="overflow-x-auto">
            <ServerDebugDrain />
            <Table>
              <TableHeader>
                <TH className="w-3/12">Name</TH>
                <TH className="w-3/12">Email</TH>
                <TH className="w-2/12">User ID</TH>
                <TH className="w-2/12">First Upload</TH>
                <TH className="w-2/12">Last Upload</TH>
              </TableHeader>
              <TableBody>
                {report.users.map((user) => (
                  <TR key={user.id}>
                    <TD className="font-medium">{user.name || "—"}</TD>
                    <TD>{user.email || "—"}</TD>
                    <TD>
                      <code className="text-foreground-muted bg-surface-alt rounded px-1 py-0.5 font-mono text-xs">
                        {user.id}
                      </code>
                    </TD>
                    <TD>{formatUploadDate(user.first_policy_upload_at)}</TD>
                    <TD>{formatUploadDate(user.last_policy_upload_at)}</TD>
                  </TR>
                ))}
              </TableBody>
            </Table>
            {report.users.length === 0 && (
              <div className="text-foreground-muted p-5 text-center">
                No signed-up users found
              </div>
            )}
          </div>
        </Card>
      </StandardPageLayout>
    </SoftmaxAdminGuard>
  );
}
