import '@/style.css'

import { Metadata } from 'next'
import { NuqsAdapter } from 'nuqs/adapters/next/app'
import { PropsWithChildren } from 'react'

import { AppProvider } from '@/app/(main)/AppContext'
import { TopMenu } from '@/app/(main)/TopMenu'
import { getAuthToken } from '@/auth/server'
import { ResetErrorProvider } from '@/components/ResetErrorContext'
import { ThemeProvider } from '@/components/ThemeProvider'
import { config } from '@/config'
import { RequestDebugPanel } from '@/lib/debug/RequestDebugPanel'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getRepo } from '@/lib/repo/server'

export default async function RootLayout({ children }: PropsWithChildren) {
  const token = await getAuthToken()
  const repo = await getRepo()

  let currentUser = ''
  try {
    const userInfo = await repo.whoami()
    currentUser = userInfo.user_email
  } catch (err: any) {
    return (
      <html lang="en">
        <body className="overflow-y-scroll">
          <div className="min-h-screen bg-surface-alt p-5 flex items-center justify-center">
            <div className="max-w-xl mx-auto bg-surface p-10 rounded-lg shadow text-center">
              <h1 className="text-foreground mb-5 text-2xl font-semibold">Policy Evaluation Dashboard</h1>
              <p className="mb-5 text-foreground-muted">Unable to connect to the evaluation server.</p>
              <p className="text-red-600 dark:text-red-400 my-5">
                Failed to connect to server: {err.message}.<br />
                Make sure the server is running at{' '}
                <a href={repo.baseUrl} target="_blank" rel="noopener noreferrer">
                  {repo.baseUrl}
                </a>
              </p>
              <p className="text-foreground-muted text-sm">Please ensure the server is running and accessible.</p>
            </div>
          </div>
        </body>
      </html>
    )
  }

  return (
    <html lang="en" suppressHydrationWarning>
      <body className="overflow-y-scroll">
        <ThemeProvider>
          <NuqsAdapter>
            <AppProvider token={token} apiBaseUrl={config.apiBaseUrl}>
              <ResetErrorProvider>
                <div className="min-h-screen font-sans flex flex-col">
                  <TopMenu currentUser={currentUser} devMode={!!config.authToken} />
                  <div className="bg-background flex-1">{children}</div>
                </div>
                <ServerDebugDrain />
                <RequestDebugPanel />
              </ResetErrorProvider>
            </AppProvider>
          </NuqsAdapter>
        </ThemeProvider>
      </body>
    </html>
  )
}

export const metadata: Metadata = {
  title: 'Observatory',
}

// Opt out of all static rendering
export const dynamic = 'force-dynamic'
