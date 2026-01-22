'use client'
import { createContext, FC, PropsWithChildren } from 'react'

import { Repo } from '../../lib/repo'

export const AppContext = createContext<{
  repo: Repo
}>({
  repo: new Repo(),
})

export const AppProvider: FC<PropsWithChildren<{ token: string | null; apiBaseUrl: string }>> = ({
  children,
  token,
  apiBaseUrl,
}) => {
  const repo = new Repo(apiBaseUrl, token)

  return <AppContext value={{ repo }}>{children}</AppContext>
}
