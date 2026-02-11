'use client'
import clsx from 'clsx'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { FC, PropsWithChildren, useCallback } from 'react'

import { AUTH_COOKIE_NAME } from '@/auth/constants'
import { Dropdown, DropdownMenu, DropdownMenuItem } from '@/components/Dropdown'
import { ThemeToggle } from '@/components/ThemeToggle'

const MenuLink: FC<PropsWithChildren<{ href: string; isActive: boolean }>> = ({ href, children, isActive = false }) => {
  return (
    <Link
      href={href}
      className={clsx(
        'py-4 px-5 no-underline border-b-2 transition-all duration-200 hover:bg-surface-alt',
        isActive ? 'border-blue-500 text-blue-500' : 'text-foreground-muted hover:text-foreground border-transparent'
      )}
    >
      {children}
    </Link>
  )
}

export const TopMenu: FC<{ currentUser: string; devMode: boolean }> = ({ currentUser, devMode }) => {
  const pathname = usePathname()
  const router = useRouter()

  const isPoliciesActive = pathname === '/' || pathname.startsWith('/policies')

  const signOut = useCallback(() => {
    document.cookie = `${AUTH_COOKIE_NAME}=; path=/; max-age=0`
    router.replace('/auth/login')
  }, [router])

  return (
    <nav className="border-b border-border-strong bg-surface px-5 flex justify-between items-center">
      <div className="max-w-7xl mx-auto flex items-center">
        <div className="flex">
          <MenuLink href="/" isActive={isPoliciesActive}>
            Policies
          </MenuLink>
          <MenuLink href="/tournament" isActive={pathname.startsWith('/tournament')}>
            Tournament
          </MenuLink>
          <MenuLink href="/episode-jobs" isActive={pathname.startsWith('/episode-job')}>
            Episode Jobs
          </MenuLink>
          <MenuLink href="/sql-query" isActive={pathname === '/sql-query'}>
            SQL Query
          </MenuLink>
          <MenuLink href="/infra/smart-plugs" isActive={pathname.startsWith('/infra/smart-plugs')}>
            Smart Plugs
          </MenuLink>
          <MenuLink href="/eval-tasks" isActive={pathname.startsWith('/eval-task')}>
            Remote Jobs
          </MenuLink>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Dropdown
          render={({ close }) => (
            <DropdownMenu>
              {devMode ? (
                <div className="px-3 py-2 text-xs text-gray-400 max-w-48">
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
          <span className="text-sm text-gray-500 cursor-pointer hover:text-gray-900 transition-colors">
            {currentUser}
          </span>
        </Dropdown>
        <ThemeToggle />
      </div>
    </nav>
  )
}
