'use client'
import { useRouter, useSelectedLayoutSegment } from 'next/navigation'
import { FC, use, useEffect, useMemo, useState } from 'react'
import { AppContext } from '@/app/(main)/AppContext'
import { Select } from '@/components/Select'
import type { SeasonDetail, SeasonVersionInfo } from '@/lib/api'

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

export const SeasonSelect: FC<{ seasons: SeasonDetail[] }> = ({ seasons }) => {
  const seasonRef = useSelectedLayoutSegment()
  const { repo } = use(AppContext)
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
  const seasonOptions: SeasonOption[] = useMemo(() => seasons.map((s) => ({ value: s.name, label: s.name })), [seasons])
  const [versions, setVersions] = useState<SeasonVersionInfo[]>([])
  const [isLoadingVersions, setIsLoadingVersions] = useState(false)
  const router = useRouter()

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
  }, [repo, selectedSeasonName])

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
      router.push(`/tournament/${option.value}`)
    }
  }

  const handleVersionChange = (option: VersionOption | null) => {
    if (!selectedSeasonName) {
      return
    }
    if (!option) {
      router.push(`/tournament/${selectedSeasonName}`)
      return
    }
    router.push(`/tournament/${formatSeasonRef(selectedSeasonName, option.value, option.canonical)}`)
  }

  return (
    <div className="flex items-center gap-3">
      <span className="text-foreground-muted font-medium">Season:</span>
      <Select
        options={seasonOptions}
        value={seasonOptions.find((o) => o.value === selectedSeasonName) || null}
        onChange={handleSeasonChange}
        size="lg"
        isSearchable={false}
        placeholder="Select season..."
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
    </div>
  )
}
