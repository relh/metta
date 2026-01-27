import { FC, useContext, useEffect, useState } from 'react'

import { AppContext } from './app/(main)/AppContext'
import { Button } from './components/Button'
import { SmartPlugStatus } from './lib/repo'

export const SmartPlugsPage: FC = () => {
  const { repo } = useContext(AppContext)
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
      <div className="p-6 text-gray-600">
        <h2 className="text-xl font-semibold mb-2">Smart Plugs</h2>
        <div>Loading status...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <h2 className="text-xl font-semibold mb-2">Smart Plugs</h2>
        <div className="text-red-600 mb-4">{error}</div>
        <Button onClick={refresh}>Retry</Button>
      </div>
    )
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-semibold">Smart Plugs</h2>
          <p className="text-sm text-gray-500">Actions require Softmax access and are logged.</p>
          {refreshedAt && <p className="text-xs text-gray-400">Last refresh: {refreshedAt}</p>}
        </div>
        <button className="px-3 py-2 rounded bg-gray-900 text-white" onClick={refresh} disabled={loading}>
          Refresh
        </button>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 uppercase text-xs">
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
              const onlineDot = plug.online == null ? 'bg-gray-400' : plug.online ? 'bg-green-500' : 'bg-red-500'
              const powerLabel = plug.is_on == null ? 'Unknown' : plug.is_on ? 'On' : 'Off'
              const apowerLabel = plug.apower == null ? '—' : `${plug.apower.toFixed(1)} W`
              const isBusy = busyKey === plug.key

              return (
                <tr key={plug.key} className="border-t border-gray-100">
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-900">{plug.label}</div>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{plug.alias || '—'}</td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center gap-2">
                      <span className={`h-2 w-2 rounded-full ${onlineDot}`} />
                      {onlineLabel}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-700">
                    {powerLabel}
                    <div className="text-xs text-gray-400">{apowerLabel}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button
                        className="px-3 py-1 rounded border border-gray-300 text-gray-700 disabled:opacity-50"
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
  )
}
