'use client'
import { useRouter } from 'next/navigation'
import { FC, use, useEffect, useState } from 'react'
import Select, { StylesConfig } from 'react-select'
import AsyncSelect from 'react-select/async'

import { AppContext } from '@/app/(main)/AppContext'
import { Button } from '@/components/Button'
import { PolicyRow, PublicPolicyVersionRow } from '@/lib/repo'

type PolicyOption = {
  value: string
  label: string
  policy: PolicyRow
}

type VersionOption = {
  value: string
  label: string
  version: PublicPolicyVersionRow
}

const selectStyles: StylesConfig<any, false, any> = {
  control: (base) => ({ ...base, minHeight: '30px', fontSize: '14px' }),
  valueContainer: (base) => ({ ...base, padding: '0 8px' }),
  indicatorsContainer: (base) => ({ ...base, height: '30px' }),
  option: (base) => ({ ...base, fontSize: '14px' }),
  menu: (base) => ({ ...base, zIndex: 50 }),
}

export const SubmitForm: FC<{
  seasonName: string
  existingPolicyVersionIds: Set<string>
}> = ({ seasonName, existingPolicyVersionIds }) => {
  const { repo } = use(AppContext)
  const [selectedPolicy, setSelectedPolicy] = useState<PolicyOption | null>(null)
  const [versions, setVersions] = useState<VersionOption[]>([])
  const [selectedVersion, setSelectedVersion] = useState<VersionOption | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null)

  const router = useRouter()

  const loadPolicies = async (inputValue: string): Promise<PolicyOption[]> => {
    if (!inputValue) return []
    const res = await repo.getPolicies({ name_fuzzy: inputValue, limit: 10 })
    return res.entries.map((p) => ({
      value: p.id,
      label: p.name,
      policy: p,
    }))
  }

  useEffect(() => {
    if (!selectedPolicy) {
      setVersions([])
      setSelectedVersion(null)
      return
    }
    let ignore = false
    repo.getVersionsForPolicy(selectedPolicy.policy.id, { limit: 50 }).then((res) => {
      if (!ignore) {
        const versionOptions = res.entries.map((v) => ({
          value: v.id,
          label: `v${v.version}`,
          version: v,
        }))
        setVersions(versionOptions)
        if (versionOptions.length > 0) {
          setSelectedVersion(versionOptions[0])
        }
      }
    })
    return () => {
      ignore = true
    }
  }, [repo, selectedPolicy])

  useEffect(() => {
    if (!submitSuccess && !submitError) return
    const timer = setTimeout(() => {
      setSubmitSuccess(null)
      setSubmitError(null)
    }, 10000)
    return () => clearTimeout(timer)
  }, [submitSuccess, submitError])

  const handleSubmit = async () => {
    if (!selectedVersion) return
    setSubmitting(true)
    setSubmitError(null)
    setSubmitSuccess(null)
    try {
      const result = await repo.submitToSeason(seasonName, selectedVersion.version.id)
      setSubmitSuccess(`Submitted to pools: ${result.pools.join(', ')}`)
      setSelectedPolicy(null)
      setSelectedVersion(null)
      router.refresh()
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setSubmitting(false)
    }
  }

  const isAlreadySubmitted = selectedVersion && existingPolicyVersionIds.has(selectedVersion.version.id)

  return (
    <div>
      <div className="text-xs text-gray-600 mb-2">Submit new player</div>
      <div className="flex gap-3 items-end">
        <div className="flex-1">
          <AsyncSelect<PolicyOption>
            instanceId="policy-select"
            value={selectedPolicy}
            onChange={setSelectedPolicy}
            loadOptions={loadPolicies}
            placeholder="Search policies..."
            isClearable
            cacheOptions
            defaultOptions={false}
            styles={selectStyles}
            noOptionsMessage={({ inputValue }) => (inputValue ? 'No policies found' : 'Type to search...')}
          />
        </div>

        {selectedPolicy && versions.length > 0 && (
          <div className="w-28">
            <Select<VersionOption>
              instanceId="version-select"
              value={selectedVersion}
              onChange={setSelectedVersion}
              options={versions}
              styles={selectStyles}
              isSearchable={false}
            />
          </div>
        )}

        <Button
          onClick={handleSubmit}
          theme="primary"
          disabled={!selectedVersion || submitting || !!isAlreadySubmitted}
        >
          {submitting ? '...' : 'Submit'}
        </Button>
      </div>

      {isAlreadySubmitted && <div className="text-xs text-amber-600 mt-1">Already in season</div>}
      {submitError && <div className="text-xs text-red-600 mt-1">{submitError}</div>}
      {submitSuccess && <div className="text-xs text-green-600 mt-1">{submitSuccess}</div>}
    </div>
  )
}
