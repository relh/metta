'use client'
import clsx from 'clsx'
import { FC, useState } from 'react'

type CopyableUriProps = {
  uri: string
  label?: string
}

export const CopyableUri: FC<CopyableUriProps> = ({ uri, label = 'Copy' }) => {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    if (typeof navigator === 'undefined' || typeof navigator.clipboard === 'undefined') {
      return
    }
    try {
      await navigator.clipboard.writeText(uri)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (error) {
      console.error('Failed to copy to clipboard:', error)
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={clsx(
        'flex items-center gap-3 px-3 py-2 rounded border text-left font-mono text-sm bg-surface',
        'transition-colors cursor-pointer w-full max-w-xl',
        copied
          ? 'border-blue-500 bg-blue-50 dark:bg-blue-950'
          : 'border-border-strong bg-surface-alt hover:border-foreground-muted'
      )}
    >
      <code className="flex-1 text-xs text-foreground break-all">{uri}</code>
      <span
        className={clsx(
          'text-xs font-semibold whitespace-nowrap',
          copied ? 'text-blue-600 dark:text-blue-400' : 'text-foreground-muted'
        )}
      >
        {copied ? 'Copied!' : label}
      </span>
    </button>
  )
}
