import 'server-only'

import { getAuthToken } from '@/auth/server'
import { config } from '@/config'

import { Repo } from './'

export async function getRepo(): Promise<Repo> {
  const token = await getAuthToken()
  return new Repo(config.apiBaseUrl, token)
}
