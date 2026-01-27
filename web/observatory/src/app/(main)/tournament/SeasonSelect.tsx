'use client'
import { useRouter, useSelectedLayoutSegment } from 'next/navigation'
import { FC } from 'react'
import Select from 'react-select'

import { SeasonDetail } from '@/lib/repo'

const seasonSelectStyles = {
  control: (base: any) => ({
    ...base,
    minHeight: '40px',
    fontSize: '1rem',
    fontWeight: 600,
    minWidth: '200px',
  }),
  singleValue: (base: any) => ({
    ...base,
    fontWeight: 600,
  }),
  option: (base: any) => ({
    ...base,
    fontSize: '1rem',
    padding: '8px 12px',
  }),
}

export const SeasonSelect: FC<{ seasons: SeasonDetail[] }> = ({ seasons }) => {
  const seasonName = useSelectedLayoutSegment()
  const seasonOptions = seasons.map((s) => ({ value: s.name, label: s.name }))
  const router = useRouter()

  const handleSeasonChange = (option: { value: string; label: string } | null) => {
    if (option) {
      router.push(`/tournament/${option.value}`)
    }
  }

  return (
    <div className="flex items-center gap-3">
      <span className="text-gray-600 font-medium">Season:</span>
      <Select
        options={seasonOptions}
        value={seasonOptions.find((o) => o.value === seasonName) || null}
        onChange={handleSeasonChange}
        styles={seasonSelectStyles}
        isSearchable={false}
        placeholder="Select season..."
        instanceId="season-select"
      />
    </div>
  )
}
