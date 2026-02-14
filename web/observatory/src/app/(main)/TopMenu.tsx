'use client'
import clsx from 'clsx'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { FC, PropsWithChildren, use } from 'react'

import { AutoRefreshBadge } from '@/components/AutoRefreshBadge'
import { Dropdown, DropdownMenu, DropdownMenuItem } from '@/components/Dropdown'
import { ThemeToggle } from '@/components/ThemeToggle'

import { AppContext } from './AppContext'
import { UserDropdown } from './UserDropdown'

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
  const { apiBaseUrl } = use(AppContext)

  const isPoliciesActive = pathname === '/' || pathname.startsWith('/policies')

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
      <div className="flex items-center gap-3">
        <AutoRefreshBadge />
        <Dropdown
          render={({ close }) => (
            <DropdownMenu>
              <DropdownMenuItem
                title="Public API"
                onClick={() => {
                  window.open(`${apiBaseUrl}/docs`, '_blank')
                  close()
                }}
              />
              <DropdownMenuItem
                title="Internal API"
                onClick={() => {
                  window.open('/api/internal/docs', '_blank')
                  close()
                }}
              />
            </DropdownMenu>
          )}
        >
          <span className="text-sm text-foreground-muted cursor-pointer hover:text-foreground transition-colors border border-border-strong rounded px-2 py-1">
            API Docs
          </span>
        </Dropdown>
        <UserDropdown currentUser={currentUser} devMode={devMode} />
        <ThemeToggle />
      </div>
    </nav>
  )
}
