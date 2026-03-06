import type { NextConfig } from 'next'

const basePath = process.env.DIAGNOSE_BASE_PATH?.trim()

const nextConfig: NextConfig = {
  output: 'standalone',
  ...(basePath ? { basePath } : {}),
}

export default nextConfig
