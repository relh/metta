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
              ? 'bg-blue-200 text-blue-800 border-blue-400'
              : 'border border-gray-300 text-gray-700 hover:bg-gray-300 hover:text-gray-900'
          )}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  )
}
