'use server'

import { config } from '@/config'

export async function getAuthUrl(redirectPath: string): Promise<string> {
  const authUrl = new URL(`${config.authServerUrl}/tokens/cli`)
  const queryParams = new URLSearchParams()
  queryParams.set('observatory_url', redirectPath)
  authUrl.searchParams.set('callback', `${config.siteUrl}/auth/callback?${queryParams.toString()}`)
  return authUrl.toString()
}
