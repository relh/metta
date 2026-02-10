import '@/style.css'

import { Metadata } from 'next'
import { PropsWithChildren } from 'react'

import { ThemeProvider } from '@/components/ThemeProvider'

export default function PublicLayout({ children }: PropsWithChildren) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="overflow-y-scroll">
        <ThemeProvider>
          <div className="min-h-screen font-sans flex flex-col bg-background">{children}</div>
        </ThemeProvider>
      </body>
    </html>
  )
}

export const metadata: Metadata = {
  title: 'Observatory',
}

export const dynamic = 'force-dynamic'
