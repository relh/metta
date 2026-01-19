import '@/style.css'

import { Metadata } from 'next'
import { NuqsAdapter } from 'nuqs/adapters/next/app'
import { PropsWithChildren } from 'react'

import { AppProvider } from '@/AppContext'
import { getAuthToken } from '@/auth/server'
import { getRepo } from '@/lib/repo/server'

import { TopMenu } from '../TopMenu'

export default async function RootLayout({ children }: PropsWithChildren) {
  const token = await getAuthToken()
  const repo = await getRepo()

  let currentUser = ''
  try {
    const userInfo = await repo.whoami()
    currentUser = userInfo.user_email
  } catch (err: any) {
    return (
      <div className="min-h-screen bg-gray-100 p-5 flex items-center justify-center">
        <div className="max-w-xl mx-auto bg-white p-10 rounded-lg shadow text-center">
          <h1 className="text-gray-800 mb-5 text-2xl font-semibold">Policy Evaluation Dashboard</h1>
          <p className="mb-5 text-gray-500">Unable to connect to the evaluation server.</p>
          <p className="text-red-600 my-5">
            Failed to connect to server: {err.message}.<br />
            Make sure the server is running at{' '}
            <a href={repo.baseUrl} target="_blank" rel="noopener noreferrer">
              {repo.baseUrl}
            </a>
          </p>
          <p className="text-gray-500 text-sm">Please ensure the server is running and accessible.</p>
        </div>
      </div>
    )
  }

  return (
    <html lang="en">
      <body className="overflow-y-scroll">
        <NuqsAdapter>
          <AppProvider token={token}>
            <div className="min-h-screen font-sans flex flex-col">
              <TopMenu currentUser={currentUser} />

              <div className="bg-gray-50 flex-1">{children}</div>
            </div>
          </AppProvider>
        </NuqsAdapter>
      </body>
    </html>
  )
}

export const metadata: Metadata = {
  title: 'Observatory',
}

// Opt out of all static rendering
export const dynamic = 'force-dynamic'
