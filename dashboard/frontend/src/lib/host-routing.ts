export type HostedService = 'dashboard' | 'bardo' | 'train-board' | 'chatprop'

function normalizeHost(value: string | null | undefined): string {
  return String(value || '')
    .split(',')[0]
    .trim()
    .toLowerCase()
    .replace(/:\d+$/, '')
}

export function serviceForHost(hostValue: string | null | undefined): HostedService {
  const host = normalizeHost(hostValue)
  if (host.startsWith('bardo.')) return 'bardo'
  if (host.startsWith('train-board.')) return 'train-board'
  if (host.startsWith('chatprop.')) return 'chatprop'
  return 'dashboard'
}
