'use client'
import { createContext, FC, PropsWithChildren } from 'react'

import { config } from './config'
import { Repo } from './lib/repo'

export const AppContext = createContext<{
  repo: Repo
}>({
  repo: new Repo(),
})

export const AppProvider: FC<PropsWithChildren<{ token: string | null }>> = ({ children, token }) => {
  const repo = new Repo(config.apiBaseUrl, token)

  return <AppContext value={{ repo }}>{children}</AppContext>
}
