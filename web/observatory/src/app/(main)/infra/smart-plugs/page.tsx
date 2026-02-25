'use client'
import { use, useEffect, useState } from 'react'

import { AppContext } from '@/app/(main)/AppContext'
import { Button } from '@/components/Button'
import { SoftmaxGuard } from '@/components/SoftmaxGuard'
import { Spinner } from '@/components/Spinner'
import { SmartPlugStatus } from '@/lib/repo'

export default function SmartPlugsPage() {
  const { repo } = use(AppContext)
  const [plugs, setPlugs] = useState<SmartPlugStatus[]>([])
  const [refreshedAt, setRefreshedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyKey, setBusyKey] = useState<string | null>(null)

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await repo.getSmartPlugStatus()
      setPlugs(response.items)
      setRefreshedAt(response.refreshed_at)
    } catch (err: any) {
      setError(err.message || 'Failed to load smart plug status')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const handleToggle = async (plug: SmartPlugStatus, on: boolean) => {
    setBusyKey(plug.key)
    setError(null)
    try {
      await repo.setSmartPlugPower({ key: plug.key, on })
      await refresh()
    } catch (err: any) {
      setError(err.message || 'Failed to update smart plug power')
    } finally {
      setBusyKey(null)
    }
  }

  if (loading && plugs.length === 0) {
    return (
      <SoftmaxGuard>
        <div className="p-6 text-foreground-muted">
          <h2 className="text-xl font-semibold mb-2">Smart Plugs</h2>
          <Spinner size="lg" />
        </div>
      </SoftmaxGuard>
    )
  }

  if (error) {
    return (
      <SoftmaxGuard>
        <div className="p-6">
          <h2 className="text-xl font-semibold mb-2">Smart Plugs</h2>
          <div className="text-red-600 mb-4">{error}</div>
          <Button onClick={refresh} theme="primary">
            Retry
          </Button>
        </div>
      </SoftmaxGuard>
    )
  }

  return (
    <SoftmaxGuard>
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold">Smart Plugs</h2>
            <p className="text-sm text-foreground-muted">Actions require Softmax access and are logged.</p>
            {refreshedAt && <p className="text-xs text-foreground-muted">Last refresh: {refreshedAt}</p>}
          </div>
          <button className="px-3 py-2 rounded bg-foreground text-surface" onClick={refresh} disabled={loading}>
            Refresh
          </button>
        </div>

        <div className="bg-surface border border-border rounded-lg overflow-hidden">
          <table className="min-w-full text-sm">
            <thead className="bg-surface-alt text-foreground-muted uppercase text-xs">
              <tr>
                <th className="px-4 py-3 text-left">Location</th>
                <th className="px-4 py-3 text-left">Alias</th>
                <th className="px-4 py-3 text-left">Online</th>
                <th className="px-4 py-3 text-left">Power</th>
                <th className="px-4 py-3 text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {plugs.map((plug) => {
                const onlineLabel = plug.online == null ? 'Unknown' : plug.online ? 'Online' : 'Offline'
                const onlineDot =
                  plug.online == null ? 'bg-foreground-muted' : plug.online ? 'bg-green-500' : 'bg-red-500'
                const powerLabel = plug.is_on == null ? 'Unknown' : plug.is_on ? 'On' : 'Off'
                const apowerLabel = plug.apower == null ? '—' : `${plug.apower.toFixed(1)} W`
                const isBusy = busyKey === plug.key

                return (
                  <tr key={plug.key} className="border-t border-border-subtle">
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">{plug.label}</div>
                    </td>
                    <td className="px-4 py-3 text-foreground-subtle">{plug.alias || '—'}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-2">
                        <span className={`h-2 w-2 rounded-full ${onlineDot}`} />
                        {onlineLabel}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground-subtle">
                      {powerLabel}
                      <div className="text-xs text-foreground-muted">{apowerLabel}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button
                          className="px-3 py-1 rounded border border-border-strong text-foreground-subtle disabled:opacity-50"
                          onClick={() => handleToggle(plug, true)}
                          disabled={isBusy || loading}
                        >
                          Turn On
                        </button>
                        <button
                          className="px-3 py-1 rounded bg-red-600 text-white disabled:opacity-50"
                          onClick={() => handleToggle(plug, false)}
                          disabled={isBusy || loading}
                        >
                          Turn Off
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </SoftmaxGuard>
  )
}
