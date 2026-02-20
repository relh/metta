'use client'
import { useRouter } from 'next/navigation'
import { FC, use, useState } from 'react'

import { AppContext } from '@/app/(main)/AppContext'
import { Button } from '@/components/Button'
import { CopyableUri } from '@/components/CopyableUri'
import { Input } from '@/components/Input'
import { Spinner } from '@/components/Spinner'
import type { ServiceAccountCreateResponse } from '@/lib/api'

type ModalState =
  | { type: 'closed' }
  | { type: 'form' }
  | { type: 'submitting' }
  | { type: 'success'; result: ServiceAccountCreateResponse }
  | { type: 'error'; error: string }

export const CreateServiceAccountModal: FC = () => {
  const { repo } = use(AppContext)
  const router = useRouter()
  const [modal, setModal] = useState<ModalState>({ type: 'closed' })
  const [name, setName] = useState('')

  const open = () => {
    setName('')
    setModal({ type: 'form' })
  }

  const close = () => {
    setModal({ type: 'closed' })
    router.refresh()
  }

  const submit = async () => {
    if (!name.trim()) return
    setModal({ type: 'submitting' })
    try {
      const result = await repo.createServiceAccount(name.trim())
      setModal({ type: 'success', result })
    } catch (err: unknown) {
      setModal({
        type: 'error',
        error: err instanceof Error ? err.message : 'Failed to create service account',
      })
    }
  }

  return (
    <>
      <Button onClick={open} theme="primary" size="md" disabled={modal.type !== 'closed'}>
        + Create
      </Button>

      {modal.type !== 'closed' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-surface border border-border rounded-lg shadow-xl w-full max-w-lg p-6 space-y-4">
            {modal.type === 'success' ? (
              <>
                <h2 className="text-base font-semibold">Service Account Created</h2>
                <p className="text-sm text-amber-600 dark:text-amber-400 font-medium">
                  Copy your token now — it won&apos;t be shown again.
                </p>
                <div className="space-y-1.5">
                  <p className="text-xs font-bold tracking-[0.04em] uppercase text-foreground-muted">Token</p>
                  <CopyableUri uri={modal.result.token} label="Copy token" />
                </div>
                <div className="flex justify-end">
                  <Button onClick={close} theme="primary">
                    Done
                  </Button>
                </div>
              </>
            ) : (
              <>
                <h2 className="text-base font-semibold">Create Service Account</h2>
                <div className="space-y-1.5">
                  <label className="text-xs font-bold tracking-[0.04em] uppercase text-foreground-muted">Name</label>
                  <Input value={name} onChange={setName} placeholder="my-service-account" />
                </div>
                {modal.type === 'error' && <p className="text-xs text-red-600">{modal.error}</p>}
                <div className="flex justify-end gap-2">
                  <Button
                    onClick={() => setModal({ type: 'closed' })}
                    theme="tertiary"
                    disabled={modal.type === 'submitting'}
                  >
                    Cancel
                  </Button>
                  <Button onClick={submit} theme="primary" disabled={modal.type === 'submitting' || !name.trim()}>
                    {modal.type === 'submitting' ? (
                      <span className="flex items-center gap-2">
                        <Spinner size="sm" />
                        Creating...
                      </span>
                    ) : (
                      'Create'
                    )}
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
