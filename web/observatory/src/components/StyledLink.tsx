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
        ? 'text-blue-600 no-underline hover:underline'
        : 'text-black no-underline hover:text-blue-600 transition-colors'
    )}
  />
)
