import { cookies } from 'next/headers'

import { config } from '@/config'

import { AUTH_COOKIE_NAME } from './constants'

export async function getAuthToken(): Promise<string | null> {
  if (config.authToken) {
    return config.authToken
  }
  const cookieStore = await cookies()
  const tokenCookie = cookieStore.get(AUTH_COOKIE_NAME)
  return tokenCookie?.value ?? null
}
