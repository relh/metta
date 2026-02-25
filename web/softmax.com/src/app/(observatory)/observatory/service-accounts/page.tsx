import { Card } from "@observatory/components/Card";
import { StandardPageLayout } from "@observatory/components/layouts/StandardPageLayout";
import { SoftmaxGuard } from "@observatory/components/SoftmaxGuard";

import { CreateServiceAccountModal } from "./CreateServiceAccountModal";
import { ServiceAccountsTable } from "./ServiceAccountsTable";

export default function ServiceAccountsPage() {
  return (
    <SoftmaxGuard>
      <StandardPageLayout>
        <div className="flex items-center justify-between">
          <h1>Service Accounts</h1>
          <CreateServiceAccountModal />
        </div>
        <p className="text-foreground-muted max-w-5xl text-balance">
          Service accounts can be used to authenticate to the API via standard
          Bearer Auth.
        </p>
        <Card padding="md">
          <ServiceAccountsTable />
        </Card>
      </StandardPageLayout>
    </SoftmaxGuard>
  );
}
