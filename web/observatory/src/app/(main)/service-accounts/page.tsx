import { Card } from '@/components/Card'
import { StandardPageLayout } from '@/components/layouts/StandardPageLayout'

import { CreateServiceAccountModal } from './CreateServiceAccountModal'
import { ServiceAccountsTable } from './ServiceAccountsTable'

export default function ServiceAccountsPage() {
  return (
    <StandardPageLayout>
      <div className="flex items-center justify-between">
        <h1>Service Accounts</h1>
        <CreateServiceAccountModal />
      </div>
      <p className="max-w-5xl text-balance text-foreground-muted">
        Service accounts can be used to authenticate to the API via standard Bearer Auth.
      </p>
      <Card padding="md">
        <ServiceAccountsTable />
      </Card>
    </StandardPageLayout>
  )
}
