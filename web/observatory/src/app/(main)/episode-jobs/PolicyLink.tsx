import { FC } from 'react'

import { StyledLink } from '@/components/StyledLink'
import { PolicyVersionSummary } from '@/lib/repo'

export function parsePolicyUri(uri: string): { uuid: string } | null {
  const match = uri.match(/^metta:\/\/policy\/([0-9a-fA-F-]{36})$/)
  if (match) {
    return { uuid: match[1] }
  }
  return null
}

export const PolicyLink: FC<{ uri: string; policy?: PolicyVersionSummary | null }> = ({ uri, policy }) => {
  if (policy) {
    const label = policy.name && policy.version !== null ? `${policy.name}:v${policy.version}` : policy.id.slice(0, 8)
    return (
      <StyledLink href={`/policies/versions/${policy.id}`} className="font-mono text-xs" title={uri}>
        {label}
      </StyledLink>
    )
  }
  const parsed = parsePolicyUri(uri)
  if (parsed) {
    return (
      <StyledLink href={`/policies/versions/${parsed.uuid}`} className="font-mono text-xs" title={uri}>
        {parsed.uuid.slice(0, 8)}
      </StyledLink>
    )
  }
  return (
    <div className="font-mono text-xs text-wrap break-all" title={uri}>
      {uri}
    </div>
  )
}
