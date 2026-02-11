'use client'

import { FC } from 'react'

import { setOutageSimulated } from '@/lib/debug/simulate-outage'

export const DisableOutageButton: FC = () => {
  return (
    <button
      className="mt-4 px-4 py-2 bg-red-600 text-white rounded-md cursor-pointer hover:bg-red-700"
      onClick={() => {
        setOutageSimulated(false)
        window.location.reload()
      }}
    >
      Disable Simulated API Outage
    </button>
  )
}
