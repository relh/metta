import type { Metadata } from 'next'

import './globals.css'

export const metadata: Metadata = {
  title: 'Diagnose | Vibeservatory',
  description: 'Cogames Diagnose surface served by Vibeservatory',
}

const THEME_BOOTSTRAP_SCRIPT = `
(() => {
  const root = document.documentElement;
  const params = new URLSearchParams(window.location.search);
  const theme = params.get('theme');
  if (theme === 'dark' || theme === 'light') {
    root.setAttribute('data-theme', theme);
    return;
  }
  if (theme === 'system') {
    root.removeAttribute('data-theme');
  }
})();
`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  )
}
