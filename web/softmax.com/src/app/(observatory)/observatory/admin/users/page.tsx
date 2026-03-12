import {
  AccessDenied,
  SoftmaxAdminGuard,
} from "@observatory/components/SoftmaxGuard";
import { Card } from "@observatory/components/Card";
import { ServerDebugDrain } from "@observatory/lib/debug/ServerDebugDrain";
import { getRepo } from "@observatory/lib/repo/server";

export default async function AdminUsersPage() {
  const repo = await getRepo();
  const userInfo = await repo.whoami();
  if (!userInfo.is_softmax_admin) {
    return (
      <AccessDenied message="This page is only available to Softmax admins." />
    );
  }

  const scaffold = await repo.getAdminUsersScaffold();

  return (
    <SoftmaxAdminGuard>
      <div className="mx-auto max-w-5xl p-5">
        <ServerDebugDrain />
        <Card title="Admin Users">
          <p className="text-foreground-muted">{scaffold.message}</p>
        </Card>
      </div>
    </SoftmaxAdminGuard>
  );
}
