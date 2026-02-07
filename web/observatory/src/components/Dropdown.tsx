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
            className="z-50 rounded-md border border-gray-300 bg-white shadow-xl"
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
      className="cursor-pointer px-3 py-1.5 text-sm text-gray-700 hover:bg-blue-50 hover:text-gray-900 transition-colors"
    >
      {title}
    </div>
  )
}
