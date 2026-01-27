import { FC, PropsWithChildren } from 'react'

export const StandardPageLayout: FC<PropsWithChildren> = ({ children }) => {
  return <div className="p-6 max-w-6xl mx-auto space-y-6">{children}</div>
}
