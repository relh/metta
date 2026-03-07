import { describe, expect, it } from 'vitest'

import { dashboardRewrites } from './rewrites'

describe('dashboardRewrites', () => {
  it('always rewrites policy-dashboard paths to root app paths first', () => {
    expect(dashboardRewrites({ nodeEnv: 'production' }).slice(0, 2)).toEqual([
      { source: '/policy-dashboard', destination: '/' },
      { source: '/policy-dashboard/:path*', destination: '/:path*' },
    ])
  })

  it('defaults to localhost surface proxies in production when explicit URLs are missing', () => {
    expect(dashboardRewrites({ nodeEnv: 'production' })).toEqual([
      { source: '/policy-dashboard', destination: '/' },
      { source: '/policy-dashboard/:path*', destination: '/:path*' },
      { source: '/bardo', destination: 'http://127.0.0.1:5175/bardo' },
      { source: '/bardo/:path*', destination: 'http://127.0.0.1:5175/bardo/:path*' },
      { source: '/pantheon', destination: 'http://127.0.0.1:5176/pantheon' },
      { source: '/pantheon/:path*', destination: 'http://127.0.0.1:5176/pantheon/:path*' },
      { source: '/diagnose', destination: 'http://127.0.0.1:5177/diagnose' },
      { source: '/diagnose/:path*', destination: 'http://127.0.0.1:5177/diagnose/:path*' },
    ])
  })

  it('adds proxy rewrites in production when explicit proxy URLs are provided', () => {
    expect(
      dashboardRewrites({
        nodeEnv: 'production',
        bardoProxyUrl: 'http://127.0.0.1:5175/bardo',
        pantheonProxyUrl: 'http://127.0.0.1:5176/pantheon',
        diagnoseProxyUrl: 'http://127.0.0.1:5177/diagnose',
      })
    ).toEqual([
      { source: '/policy-dashboard', destination: '/' },
      { source: '/policy-dashboard/:path*', destination: '/:path*' },
      { source: '/bardo', destination: 'http://127.0.0.1:5175/bardo' },
      { source: '/bardo/:path*', destination: 'http://127.0.0.1:5175/bardo/:path*' },
      { source: '/pantheon', destination: 'http://127.0.0.1:5176/pantheon' },
      { source: '/pantheon/:path*', destination: 'http://127.0.0.1:5176/pantheon/:path*' },
      { source: '/diagnose', destination: 'http://127.0.0.1:5177/diagnose' },
      { source: '/diagnose/:path*', destination: 'http://127.0.0.1:5177/diagnose/:path*' },
    ])
  })

  it('defaults to localhost proxies outside production', () => {
    expect(dashboardRewrites({ nodeEnv: 'development' })).toEqual([
      { source: '/policy-dashboard', destination: '/' },
      { source: '/policy-dashboard/:path*', destination: '/:path*' },
      { source: '/bardo', destination: 'http://127.0.0.1:5175/bardo' },
      { source: '/bardo/:path*', destination: 'http://127.0.0.1:5175/bardo/:path*' },
      { source: '/pantheon', destination: 'http://127.0.0.1:5176/pantheon' },
      { source: '/pantheon/:path*', destination: 'http://127.0.0.1:5176/pantheon/:path*' },
      { source: '/diagnose', destination: 'http://127.0.0.1:5177/diagnose' },
      { source: '/diagnose/:path*', destination: 'http://127.0.0.1:5177/diagnose/:path*' },
    ])
  })
})
