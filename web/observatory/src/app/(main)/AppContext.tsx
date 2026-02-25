'use client'
import { createContext, FC, PropsWithChildren, useCallback, useMemo, useState } from 'react'

import { addEntries } from '@/lib/debug/request-log'

import { Repo } from '../../lib/repo'

export const AppContext = createContext<{
  repo: Repo
  token: string | null
  apiBaseUrl: string
  isSoftmaxTeamMember: boolean
  isActuallySoftmaxTeamMember: boolean
  actAsExternal: boolean
  toggleActAsExternal: () => void
}>({
  repo: new Repo(),
  token: null,
  apiBaseUrl: 'http://localhost:8000',
  isSoftmaxTeamMember: false,
  isActuallySoftmaxTeamMember: false,
  actAsExternal: false,
  toggleActAsExternal: () => {},
})

export const AppProvider: FC<
  PropsWithChildren<{ token: string | null; apiBaseUrl: string; isSoftmaxTeamMember: boolean }>
> = ({ children, token, apiBaseUrl, isSoftmaxTeamMember: isActuallySoftmaxTeamMember }) => {
  const [actAsExternal, setActAsExternal] = useState(false)
  const onRequest = useCallback((entry: import('../../lib/repo').RequestLogEntry) => addEntries([entry]), [])
  const repo = useMemo(
    () => new Repo(apiBaseUrl, token, onRequest, actAsExternal),
    [apiBaseUrl, token, onRequest, actAsExternal]
  )

  const toggleActAsExternal = useCallback(() => setActAsExternal((v) => !v), [])
  const isSoftmaxTeamMember = isActuallySoftmaxTeamMember && !actAsExternal

  return (
    <AppContext
      value={{
        repo,
        token,
        apiBaseUrl,
        isSoftmaxTeamMember,
        isActuallySoftmaxTeamMember,
        actAsExternal,
        toggleActAsExternal,
      }}
    >
      {children}
    </AppContext>
  )
}
