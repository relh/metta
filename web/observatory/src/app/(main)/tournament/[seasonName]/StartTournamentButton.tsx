'use client'

import { useRouter } from 'next/navigation'
import { FC, use, useState } from 'react'

import { AppContext } from '@/app/(main)/AppContext'
import { Button } from '@/components/Button'

export const StartTournamentButton: FC<{ seasonName: string; policyCount: number }> = ({ seasonName, policyCount }) => {
  const { repo } = use(AppContext)
  const router = useRouter()
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleStart = async () => {
    setStarting(true)
    setError(null)
    try {
      await repo.startSeason(seasonName)
      router.refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start tournament')
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-foreground-muted text-sm">
        {policyCount} {policyCount === 1 ? 'policy' : 'policies'} in pool. Start the tournament to begin stage 1
        evaluation.
      </p>
      <Button onClick={handleStart} theme="primary" disabled={starting || policyCount === 0}>
        {starting ? 'Starting...' : 'Start Tournament'}
      </Button>
      {error && <p className="text-red-600 text-xs">{error}</p>}
    </div>
  )
}
