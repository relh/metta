'use client'
import clsx from 'clsx'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { FC, PropsWithChildren } from 'react'

export type LinkTab = {
  id: string
  label: string
  href: string
  isActive?: boolean
}

type LinkTabsProps = PropsWithChildren<{
  tabs: LinkTab[]
}>

export const LinkTabs: FC<LinkTabsProps> = ({ tabs }) => {
  const pathname = usePathname()

  return (
    <div className="flex gap-2">
      {tabs.map((tab) => (
        <Link
          key={tab.id}
          href={tab.href}
          className={clsx(
            'no-underline rounded-full px-4 py-2 text-sm font-medium border',
            pathname === tab.href
              ? 'bg-blue-200 dark:bg-blue-900 text-blue-800 dark:text-blue-200 border-blue-400 dark:border-blue-700'
              : 'border border-border-strong text-foreground-subtle hover:bg-surface-alt hover:text-foreground'
          )}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  )
}
