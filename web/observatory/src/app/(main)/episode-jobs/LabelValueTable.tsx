import { FC, ReactNode } from 'react'

export const LabelRow: FC<{ label: string; extra?: ReactNode; children: ReactNode }> = ({ label, extra, children }) => (
  <tr>
    <td className="pr-2 text-gray-600 whitespace-nowrap">{label}:</td>
    <td className="text-right">{children}</td>
    {extra !== undefined && <td className="pl-2 text-right">{extra}</td>}
  </tr>
)

export const LabelValueTable: FC<{ children: ReactNode }> = ({ children }) => (
  <table className="w-full text-xs">
    <tbody>{children}</tbody>
  </table>
)
