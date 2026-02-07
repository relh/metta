'use client'
import { createContext, FC, PropsWithChildren } from 'react'

import { addEntries } from '@/lib/debug/request-log'

import { Repo } from '../../lib/repo'

export const AppContext = createContext<{
  repo: Repo
  token: string | null
  apiBaseUrl: string
}>({
  repo: new Repo(),
  token: null,
  apiBaseUrl: 'http://localhost:8000',
})

export const AppProvider: FC<PropsWithChildren<{ token: string | null; apiBaseUrl: string }>> = ({
  children,
  token,
  apiBaseUrl,
}) => {
  const repo = new Repo(apiBaseUrl, token, (entry) => addEntries([entry]))

  return <AppContext value={{ repo, token, apiBaseUrl }}>{children}</AppContext>
}
