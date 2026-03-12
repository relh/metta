import {
  AccessDenied,
  SoftmaxAdminGuard,
} from "@observatory/components/SoftmaxGuard";
import { Card } from "@observatory/components/Card";
import { StandardPageLayout } from "@observatory/components/layouts/StandardPageLayout";
import { ServerDebugDrain } from "@observatory/lib/debug/ServerDebugDrain";
import { getRepo } from "@observatory/lib/repo/server";

import { AdminUsersTable } from "./AdminUsersTable";

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
          <h1>Users</h1>
          <p className="text-foreground-muted max-w-4xl text-balance">
            All signed-up users, joined with signup, upload, and tournament
            submission timestamps from Observatory.
          </p>
        </div>
        <Card padding="md">
          <ServerDebugDrain />
          <AdminUsersTable users={report.users} />
        </Card>
      </StandardPageLayout>
    </SoftmaxAdminGuard>
  );
}
