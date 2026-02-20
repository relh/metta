import { parseAsInteger, parseAsString } from 'nuqs/server'

export const nuqsParams = {
  pool_name: parseAsString.withDefault(''),
  eliminated: parseAsString.withDefault(''),
  policy_version_id: parseAsString.withDefault(''),
  teams_page: parseAsInteger.withDefault(0),
}
