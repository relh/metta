import type { Metadata } from 'next'

import './globals.css'

export const metadata: Metadata = {
  title: 'Standalone Dashboard',
  description: 'Standalone dashboard + diagnostics app',
}

const THEME_BOOTSTRAP_SCRIPT = `
(() => {
  const root = document.documentElement;
  const params = new URLSearchParams(window.location.search);
  const theme = params.get('theme');
  if (theme === 'dark' || theme === 'light') {
    root.setAttribute('data-theme', theme);
    root.style.colorScheme = theme;
    return;
  }
  if (theme === 'system') {
    root.removeAttribute('data-theme');
    root.style.colorScheme = '';
    return;
  }
  const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  root.style.colorScheme = isDark ? 'dark' : 'light';
})();
`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  )
}
