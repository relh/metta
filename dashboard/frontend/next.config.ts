import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/policy-dashboard',
        destination: '/',
      },
      {
        source: '/policy-dashboard/:path*',
        destination: '/:path*',
      },
    ]
  },
}

export default nextConfig
