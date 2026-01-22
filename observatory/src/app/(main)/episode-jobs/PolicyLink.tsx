import { FC } from 'react'

import { StyledLink } from '@/components/StyledLink'

export function parsePolicyUri(uri: string): { uuid: string } | null {
  const match = uri.match(/^metta:\/\/policy\/([0-9a-fA-F-]{36})$/)
  if (match) {
    return { uuid: match[1] }
  }
  return null
}

export const PolicyLink: FC<{ uri: string }> = ({ uri }) => {
  const parsed = parsePolicyUri(uri)
  if (parsed) {
    return (
      <StyledLink href={`/policies/versions/${parsed.uuid}`} className="font-mono text-xs" title={uri}>
        {uri}
      </StyledLink>
    )
  }
  return (
    <div className="font-mono text-xs text-wrap break-all" title={uri}>
      {uri}
    </div>
  )
}
