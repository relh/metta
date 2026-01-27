'use client'
import clsx from 'clsx'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { FC, PropsWithChildren } from 'react'

const MenuLink: FC<PropsWithChildren<{ href: string; isActive: boolean }>> = ({ href, children, isActive = false }) => {
  return (
    <Link
      href={href}
      className={clsx(
        'py-4 px-5 no-underline border-b-2 transition-all duration-200 hover:bg-gray-100',
        isActive ? 'border-blue-500 text-blue-500' : 'text-gray-500 hover:text-gray-900 border-transparent'
      )}
    >
      {children}
    </Link>
  )
}

export const TopMenu: FC<{ currentUser: string }> = ({ currentUser }) => {
  const pathname = usePathname()

  const isPoliciesActive = pathname === '/' || pathname.startsWith('/policies')

  return (
    <nav className="border-b border-gray-300 px-5 flex justify-between items-center">
      <div className="max-w-7xl mx-auto flex items-center">
        <div className="flex">
          <MenuLink href="/" isActive={isPoliciesActive}>
            Policies
          </MenuLink>
          <MenuLink href="/tournament" isActive={pathname.startsWith('/tournament')}>
            Tournament
          </MenuLink>
          <MenuLink href="/eval-tasks" isActive={pathname.startsWith('/eval-task')}>
            Remote Jobs
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
        </div>
      </div>
      <div className="flex items-center">
        <span className="text-sm text-gray-500">{currentUser}</span>
      </div>
    </nav>
  )
}
