import type { NextConfig } from 'next'

const basePath = process.env.PANTHEON_BASE_PATH?.trim()

const nextConfig: NextConfig = {
  output: 'standalone',
  ...(basePath ? { basePath } : {}),
}

export default nextConfig
