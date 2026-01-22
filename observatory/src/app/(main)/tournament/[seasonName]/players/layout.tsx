import { Suspense } from 'react'

import { Card } from '@/components/Card'
import { Spinner } from '@/components/Spinner'

export default function PlayersLayout({ children }: { children: React.ReactNode }) {
  return (
    <Card title="Players">
      <Suspense
        fallback={
          <div className="grid place-items-center min-h-80">
            <Spinner size="lg" />
          </div>
        }
      >
        {children}
      </Suspense>
    </Card>
  )
}

export async function generateMetadata({ params }: PageProps<'/tournament/[seasonName]/players'>) {
  const { seasonName } = await params
  return {
    title: `Players for Season ${seasonName} | Observatory`,
  }
}
