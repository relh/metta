import type { NextConfig } from 'next'
import { dashboardRewrites } from './src/lib/rewrites'

const nextConfig: NextConfig = {
  output: 'standalone',
  async rewrites() {
    return dashboardRewrites({
      bardoProxyUrl: process.env.BARDO_PROXY_URL,
      pantheonProxyUrl: process.env.PANTHEON_PROXY_URL,
      diagnoseProxyUrl: process.env.DIAGNOSE_PROXY_URL,
      nodeEnv: process.env.NODE_ENV,
    })
  },
}

export default nextConfig
