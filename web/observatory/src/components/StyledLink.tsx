import clsx from 'clsx'
import Link, { LinkProps } from 'next/link'
import { ComponentProps, FC } from 'react'

export const StyledLink: FC<LinkProps & ComponentProps<'a'> & { theme?: 'normal' | 'muted' }> = ({
  className,
  theme = 'normal',
  ...props
}) => (
  <Link
    {...props}
    className={clsx(
      className,
      theme === 'normal'
        ? 'text-blue-600 dark:text-blue-400 no-underline hover:underline'
        : 'text-foreground no-underline hover:text-blue-600 dark:hover:text-blue-400 transition-colors'
    )}
  />
)
