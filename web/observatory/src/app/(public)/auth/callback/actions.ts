'use server'

import { config } from '@/config'

interface ValidationResult {
  valid: boolean
  isSoftmaxTeamMember: boolean
  error?: string
}

export async function validateToken(token: string): Promise<ValidationResult> {
  try {
    const response = await fetch(`${config.authServerUrl}/validate`, {
      headers: { 'X-Auth-Token': token },
    })
    if (response.ok) {
      const data = await response.json()
      return {
        valid: !!data.valid,
        isSoftmaxTeamMember: !!data.user?.isSoftmaxTeamMember,
      }
    }
    return { valid: false, isSoftmaxTeamMember: false, error: 'Token validation failed' }
  } catch {
    return { valid: false, isSoftmaxTeamMember: false, error: 'Failed to connect to auth service' }
  }
}
