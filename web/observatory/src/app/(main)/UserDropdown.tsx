'use client'
import { useRouter } from 'next/navigation'
import { FC, useCallback } from 'react'

import { AUTH_COOKIE_NAME } from '@/auth/constants'
import { Dropdown, DropdownMenu, DropdownMenuItem } from '@/components/Dropdown'
import { useDebugPanelVisible } from '@/lib/debug/useDebugPanelVisible'

export const UserDropdown: FC<{ currentUser: string; devMode: boolean }> = ({ currentUser, devMode }) => {
  const router = useRouter()
  const { isVisible: debugPanelVisible, toggle: toggleDebugPanel } = useDebugPanelVisible()

  const signOut = useCallback(() => {
    document.cookie = `${AUTH_COOKIE_NAME}=; path=/; max-age=0`
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
