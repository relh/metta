import { PropsWithChildren } from 'react'

import { ResetErrorProvider } from '@/components/ResetErrorContext'

export default function EpisodeJobsLayout({ children }: PropsWithChildren) {
  return <ResetErrorProvider>{children}</ResetErrorProvider>
}
