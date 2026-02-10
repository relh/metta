// Adapted from gridworks Dropdown component
// (TODO: reuse through web/common package later)
'use client'

import { flip, FloatingPortal, offset, useClick, useDismiss, useFloating, useInteractions } from '@floating-ui/react'
import { FC, PropsWithChildren, ReactNode, useCallback, useState } from 'react'

export const Dropdown: FC<
  PropsWithChildren<{
    render(options: { close(): void }): ReactNode
  }>
> = ({ render, children }) => {
  const [isOpen, setIsOpen] = useState(false)

  const { refs, floatingStyles, context } = useFloating({
    open: isOpen,
    onOpenChange: setIsOpen,
    placement: 'bottom-start',
    middleware: [offset(4), flip()],
  })

  const click = useClick(context)
  const dismiss = useDismiss(context)
  const { getReferenceProps, getFloatingProps } = useInteractions([click, dismiss])

  const close = useCallback(() => setIsOpen(false), [])

  return (
    <>
      <div ref={refs.setReference} {...getReferenceProps()}>
        {children}
      </div>
      {isOpen && (
        <FloatingPortal>
          <div
            ref={refs.setFloating}
            className="z-50 rounded-md border border-border-strong bg-surface shadow-xl"
            style={floatingStyles}
            {...getFloatingProps()}
          >
            {render({ close })}
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

export const DropdownMenu: FC<PropsWithChildren> = ({ children }) => {
  return <div className="py-1">{children}</div>
}

export const DropdownMenuItem: FC<{ title: string; onClick: () => void }> = ({ title, onClick }) => {
  return (
    <div
      onClick={onClick}
      className="cursor-pointer px-3 py-1.5 text-sm text-foreground-subtle hover:bg-blue-50 dark:hover:bg-blue-950 hover:text-foreground transition-colors"
    >
      {title}
    </div>
  )
}
