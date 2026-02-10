import { FC, PropsWithChildren } from 'react'

export const Tag: FC<PropsWithChildren> = ({ children }) => {
  return (
    <span className="border border-blue-300 dark:border-blue-700 rounded px-2 py-0.5 text-xs bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 leading-none">
      {children}
    </span>
  )
}
