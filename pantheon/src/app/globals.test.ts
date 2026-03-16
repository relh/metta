import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

const css = readFileSync(resolve(process.cwd(), 'src/app/globals.css'), 'utf8')

describe('Pantheon theme styles', () => {
  let styleElement: HTMLStyleElement

  beforeEach(() => {
    styleElement = document.createElement('style')
    styleElement.textContent = css
    document.head.append(styleElement)
  })

  afterEach(() => {
    styleElement.remove()
    document.documentElement.removeAttribute('data-theme')
  })

  it('defines dark hall and story surfaces for embedded dark mode', () => {
    document.documentElement.setAttribute('data-theme', 'dark')

    const rootStyle = getComputedStyle(document.documentElement)

    expect(rootStyle.getPropertyValue('--fame-surface').trim()).toBe('#0f1d2e')
    expect(rootStyle.getPropertyValue('--same-surface').trim()).toBe('#1f1730')
    expect(rootStyle.getPropertyValue('--lame-surface').trim()).toBe('#2b1519')
    expect(rootStyle.getPropertyValue('--story-surface').trim()).toBe('#172133')
    expect(rootStyle.getPropertyValue('--muted-fg').trim()).toBe('#9db0cc')
  })
})
