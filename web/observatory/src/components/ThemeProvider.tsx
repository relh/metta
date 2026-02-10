'use client'

import { ThemeProvider as NextThemesProvider } from 'next-themes'
import { type FC, type PropsWithChildren } from 'react'

export const ThemeProvider: FC<PropsWithChildren> = ({ children }) => (
  <NextThemesProvider attribute="class" defaultTheme="system">
    {children}
  </NextThemesProvider>
)
