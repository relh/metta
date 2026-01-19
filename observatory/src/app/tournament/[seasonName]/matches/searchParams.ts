import { parseAsArrayOf, parseAsInteger, parseAsString } from 'nuqs/server'

export const nuqsParams = {
  pool_names: parseAsArrayOf(parseAsString).withDefault([]),
  policy_version_ids: parseAsArrayOf(parseAsString).withDefault([]),
  match_page: parseAsInteger.withDefault(0),
}
