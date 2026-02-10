import clsx from 'clsx'
import { FC } from 'react'

export function getButtonClassName(
  size: 'sm' | 'md',
  theme: 'primary' | 'secondary' | 'tertiary',
  disabled: boolean = false
) {
  return clsx(
    'rounded-md',
    size === 'sm' && 'px-2 py-0.5 text-xs border',
    size === 'md' && 'px-4 py-1 text-sm border-2',
    theme === 'primary' && ['border-blue-500 bg-blue-500 text-white', !disabled && 'hover:bg-blue-600'],
    theme === 'secondary' && [
      'border-blue-400 text-blue-500 bg-surface',
      !disabled && 'hover:bg-blue-100 dark:hover:bg-blue-900/30',
    ],
    theme === 'tertiary' && [
      'border-border-strong text-foreground-muted bg-transparent',
      !disabled && 'hover:bg-surface-alt',
    ],
    disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
  )
}

export const Button: FC<{
  onClick?: () => void
  children: React.ReactNode
  theme?: 'primary' | 'secondary'
  type?: 'button' | 'submit'
  size?: 'sm' | 'md'
  disabled?: boolean
}> = ({ onClick, children, theme = 'secondary', type = 'button', size = 'md', disabled = false }) => {
  return (
    <button className={getButtonClassName(size, theme, disabled)} onClick={onClick} type={type} disabled={disabled}>
      {children}
    </button>
  )
}
