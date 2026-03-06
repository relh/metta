import { redirect } from 'next/navigation'

type PantheonPageSearchParams = Record<string, string | string[] | undefined>

function copySearchParams(searchParams: PantheonPageSearchParams): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(searchParams)) {
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

export default async function PantheonPage(props: { searchParams: Promise<PantheonPageSearchParams> }) {
  const query = copySearchParams(await props.searchParams)
  redirect(query ? `/pantheon/v0?${query}` : '/pantheon/v0')
}
