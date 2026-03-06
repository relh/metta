import { redirect } from 'next/navigation'

type PantheonV0SearchParams = Record<string, string | string[] | undefined>

function buildPantheonQuery(searchParams: PantheonV0SearchParams): string {
  const query = new URLSearchParams()
  query.set('tab', 'pantheon')

  for (const [key, value] of Object.entries(searchParams)) {
    if (key === 'tab') continue
    if (typeof value === 'string') {
      const trimmed = value.trim()
      if (trimmed) {
        query.set(key, trimmed)
      }
      continue
    }
    if (!Array.isArray(value)) continue
    for (const item of value) {
      const trimmed = item.trim()
      if (trimmed) {
        query.append(key, trimmed)
      }
    }
  }

  return query.toString()
}

export default async function PantheonV0Page(props: { searchParams: Promise<PantheonV0SearchParams> }) {
  redirect(`/?${buildPantheonQuery(await props.searchParams)}`)
}
