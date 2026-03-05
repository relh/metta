import { describe, expect, it } from 'vitest'

import { serviceForHost } from './host-routing'

describe('serviceForHost', () => {
  it('routes known vibeservatory hosts to dedicated apps', () => {
    expect(serviceForHost('bardo.vibeservatory.softmax-research.net')).toBe('bardo')
    expect(serviceForHost('train-board.vibeservatory.softmax-research.net')).toBe('train-board')
    expect(serviceForHost('chatprop.vibeservatory.softmax-research.net')).toBe('chatprop')
  })

  it('normalizes host casing and port suffixes', () => {
    expect(serviceForHost('BARDO.vibeservatory.softmax-research.net:443')).toBe('bardo')
    expect(serviceForHost('chatprop.vibeservatory.softmax-research.net, proxy.local')).toBe('chatprop')
  })

  it('falls back to dashboard for unknown hosts', () => {
    expect(serviceForHost('policy-dashboard.vibeservatory.softmax-research.net')).toBe('dashboard')
    expect(serviceForHost('')).toBe('dashboard')
  })
})
