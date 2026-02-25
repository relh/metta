'use client'
import { useRouter } from 'next/navigation'
import { FC, use, useCallback } from 'react'

import { clearAuthCookies } from '@/auth/browser'
import { Dropdown, DropdownMenu, DropdownMenuItem } from '@/components/Dropdown'
import { useDebugPanelVisible } from '@/lib/debug/useDebugPanelVisible'

import { AppContext } from './AppContext'

export const UserDropdown: FC<{ currentUser: string; devMode: boolean }> = ({ currentUser, devMode }) => {
  const router = useRouter()
  const { isVisible: debugPanelVisible, toggle: toggleDebugPanel } = useDebugPanelVisible()
  const { isActuallySoftmaxTeamMember, actAsExternal, toggleActAsExternal } = use(AppContext)

  const signOut = useCallback(() => {
    clearAuthCookies()
    router.replace('/auth/login')
  }, [router])

  return (
    <Dropdown
      render={({ close }) => (
        <DropdownMenu>
          <DropdownMenuItem
            title={debugPanelVisible ? 'Hide API requests panel' : 'Show API requests panel'}
            onClick={() => {
              toggleDebugPanel()
              close()
            }}
          />
          {isActuallySoftmaxTeamMember && (
            <>
              <DropdownMenuItem
                title={actAsExternal ? 'Act as Softmax user' : 'Act as external user'}
                onClick={() => {
                  toggleActAsExternal()
                  close()
                }}
              />
              {!actAsExternal && (
                <DropdownMenuItem
                  title="Service Accounts"
                  onClick={() => {
                    router.push('/service-accounts')
                  }}
                />
              )}
            </>
          )}
          {devMode ? (
            <div className="px-3 py-2 text-xs text-foreground-subtle max-w-48">
              Auth is set via DEV_AUTH_TOKEN. Sign out is not available in dev mode.
            </div>
          ) : (
            <DropdownMenuItem
              title="Sign out"
              onClick={() => {
                close()
                signOut()
              }}
            />
          )}
        </DropdownMenu>
      )}
    >
      <span className="text-sm text-foreground-muted cursor-pointer hover:text-foreground transition-colors">
        {currentUser}
      </span>
    </Dropdown>
  )
}
