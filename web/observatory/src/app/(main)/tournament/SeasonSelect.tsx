'use client'
import { useRouter, useSearchParams, useSelectedLayoutSegment } from 'next/navigation'
import { FC, use, useEffect, useMemo, useState } from 'react'
import { AppContext } from '@/app/(main)/AppContext'
import { Button } from '@/components/Button'
import { Input } from '@/components/Input'
import { Select } from '@/components/Select'
import type { SeasonSummary, SeasonVersionInfo } from '@/lib/api'
import { seasonTabModeForName, type SeasonTabMode } from '@/lib/tournament/tabMode'

type SeasonOption = { value: string; label: string }
type VersionOption = { value: number; label: string; canonical: boolean }

const parseSeasonRef = (seasonRef: string | null) => {
  if (!seasonRef) {
    return { name: null, version: null }
  }
  const vIdx = seasonRef.lastIndexOf(':v')
  if (vIdx > 0) {
    const name = seasonRef.slice(0, vIdx)
    const version = Number(seasonRef.slice(vIdx + 2))
    if (Number.isFinite(version)) {
      return { name, version }
    }
  }
  const colonIdx = seasonRef.lastIndexOf(':')
  if (colonIdx > 0) {
    const name = seasonRef.slice(0, colonIdx)
    const version = Number(seasonRef.slice(colonIdx + 1))
    if (Number.isFinite(version)) {
      return { name, version }
    }
  }
  return { name: seasonRef, version: null }
}

const formatSeasonRef = (name: string, version: number | null, canonical: boolean) =>
  version && !canonical ? `${name}:v${version}` : name

export const SeasonSelect: FC<{ seasons: SeasonSummary[] }> = ({ seasons }) => {
  const seasonRef = useSelectedLayoutSegment()
  const searchParams = useSearchParams()
  const { repo } = use(AppContext)
  const [rollError, setRollError] = useState<string | null>(null)
  const [isRolling, setIsRolling] = useState(false)
  const [rollCompatVersion, setRollCompatVersion] = useState('')
  const [rollMigrateActivePlayers, setRollMigrateActivePlayers] = useState(false)
  const decodedSeasonRef = useMemo(() => {
    if (!seasonRef) {
      return null
    }
    try {
      return decodeURIComponent(seasonRef)
    } catch {
      return seasonRef
    }
  }, [seasonRef])
  const { name: selectedSeasonName, version: selectedSeasonVersion } = useMemo(
    () => parseSeasonRef(decodedSeasonRef),
    [decodedSeasonRef]
  )
  const selectedSeason = useMemo(
    () => seasons.find((season) => season.name === selectedSeasonName) ?? null,
    [seasons, selectedSeasonName]
  )
  const freeplaySeasons = useMemo(
    () => seasons.filter((season) => seasonTabModeForName(season.name) === 'freeplay'),
    [seasons]
  )
  const tournamentSeasons = useMemo(
    () => seasons.filter((season) => seasonTabModeForName(season.name) === 'tournament'),
    [seasons]
  )
  const selectedMode: SeasonTabMode = useMemo(() => {
    const modeParam = searchParams.get('mode')
    if (modeParam === 'freeplay' || modeParam === 'tournament') {
      return modeParam
    }
    if (selectedSeason) {
      return seasonTabModeForName(selectedSeason.name)
    }
    if (freeplaySeasons.length > 0) {
      return 'freeplay'
    }
    return 'tournament'
  }, [freeplaySeasons.length, searchParams, selectedSeason])
  const tabSeasons = selectedMode === 'freeplay' ? freeplaySeasons : tournamentSeasons
  const seasonOptions: SeasonOption[] = useMemo(() => {
    const options = tabSeasons.map((season) => ({ value: season.name, label: season.name }))
    if (selectedSeasonName && !options.some((option) => option.value === selectedSeasonName)) {
      options.unshift({ value: selectedSeasonName, label: selectedSeasonName })
    }
    return options
  }, [selectedSeasonName, tabSeasons])
  const [versions, setVersions] = useState<SeasonVersionInfo[]>([])
  const [isLoadingVersions, setIsLoadingVersions] = useState(false)
  const [versionsRefreshNonce, setVersionsRefreshNonce] = useState(0)
  const router = useRouter()
  const withMode = (path: string, mode: SeasonTabMode = selectedMode) => `${path}?mode=${mode}`

  useEffect(() => {
    let cancelled = false
    if (!selectedSeasonName) {
      setVersions([])
      return
    }
    setVersions([])
    setIsLoadingVersions(true)
    repo
      .getSeasonVersions(selectedSeasonName)
      .then((data) => {
        if (!cancelled) {
          setVersions(data)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setVersions([])
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingVersions(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [repo, selectedSeasonName, versionsRefreshNonce])

  const versionOptions: VersionOption[] = useMemo(
    () =>
      versions
        .slice()
        .sort((a, b) => b.version - a.version)
        .map((v) => ({
          value: v.version,
          canonical: v.canonical,
          label: v.canonical ? `v${v.version} (current)` : `v${v.version}`,
        })),
    [versions]
  )

  const selectedVersion = useMemo(() => {
    if (!selectedSeasonName || versionOptions.length === 0) {
      return null
    }
    if (selectedSeasonVersion) {
      return versionOptions.find((o) => o.value === selectedSeasonVersion) || null
    }
    return versionOptions.find((o) => o.canonical) || versionOptions[0]
  }, [selectedSeasonName, selectedSeasonVersion, versionOptions])

  const handleSeasonChange = (option: SeasonOption | null) => {
    if (option) {
      router.push(withMode(`/tournament/${option.value}`))
    }
  }

  const handleVersionChange = (option: VersionOption | null) => {
    if (!selectedSeasonName) {
      return
    }
    if (!option) {
      router.push(withMode(`/tournament/${selectedSeasonName}`))
      return
    }
    router.push(withMode(`/tournament/${formatSeasonRef(selectedSeasonName, option.value, option.canonical)}`))
  }

  const nextVersion = useMemo(() => {
    if (versions.length === 0) {
      return null
    }
    return Math.max(...versions.map((version) => version.version)) + 1
  }, [versions])
  const isBusy = isRolling || isLoadingVersions

  const handleRollSeason = async () => {
    if (!selectedSeasonName || !selectedSeason?.id || nextVersion === null) {
      return
    }
    const compatVersion = rollCompatVersion.trim()
    if (!compatVersion) {
      setRollError('Compat version is required')
      return
    }
    setIsRolling(true)
    setRollError(null)
    try {
      const newSeason = await repo.rollSeason(selectedSeason.id, compatVersion, rollMigrateActivePlayers)
      setRollCompatVersion('')
      setRollMigrateActivePlayers(false)
      setVersionsRefreshNonce((current) => current + 1)
      router.push(withMode(`/tournament/${newSeason.name}`, 'freeplay'))
      router.refresh()
    } catch (error: unknown) {
      setRollError(error instanceof Error ? error.message : 'Failed to roll season')
    } finally {
      setIsRolling(false)
    }
  }

  return (
    <div className="space-y-3">
      {rollError && <div className="text-red-500 text-sm">{rollError}</div>}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-foreground-muted font-medium">Season:</span>
        <Select
          options={seasonOptions}
          value={seasonOptions.find((option) => option.value === selectedSeasonName) || null}
          onChange={handleSeasonChange}
          size="lg"
          isSearchable={false}
          placeholder={`Select ${selectedMode === 'freeplay' ? 'freeplay' : 'tournament'} season...`}
          instanceId="season-select"
        />
        <span className="text-foreground-muted font-medium">Version:</span>
        <Select
          options={versionOptions}
          value={selectedVersion}
          onChange={handleVersionChange}
          size="lg"
          isSearchable={false}
          placeholder={selectedSeasonName ? 'Select version...' : 'Select season first'}
          instanceId="season-version-select"
          isDisabled={!selectedSeasonName || isLoadingVersions}
        />
        {selectedMode === 'freeplay' && selectedSeasonName && nextVersion !== null && (
          <>
            <div className="w-44">
              <Input
                value={rollCompatVersion}
                onChange={setRollCompatVersion}
                placeholder="Compat version (required)"
                size="sm"
              />
            </div>
            <label className="inline-flex items-center gap-2 text-xs text-foreground-muted">
              <input
                type="checkbox"
                checked={rollMigrateActivePlayers}
                onChange={(event) => setRollMigrateActivePlayers(event.target.checked)}
                className="h-3.5 w-3.5"
              />
              Migrate active players
            </label>
            <Button
              onClick={handleRollSeason}
              size="sm"
              disabled={isBusy || !rollCompatVersion.trim() || !selectedSeason?.id}
            >
              {isRolling ? 'Creating...' : `Make new v${nextVersion}`}
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
