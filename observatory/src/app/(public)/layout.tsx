import '@/style.css'

import { Metadata } from 'next'
import { PropsWithChildren } from 'react'

export default function PublicLayout({ children }: PropsWithChildren) {
  return (
    <html lang="en">
      <body className="overflow-y-scroll">
        <div className="min-h-screen font-sans flex flex-col bg-gray-50">{children}</div>
      </body>
    </html>
  )
}

export const metadata: Metadata = {
  title: 'Observatory',
}

export const dynamic = 'force-dynamic'
