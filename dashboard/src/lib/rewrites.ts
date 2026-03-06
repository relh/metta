export type DashboardRewrite = { source: string; destination: string }

function trimToNull(value: string | undefined): string | null {
  const trimmed = value?.trim()
  return trimmed ? trimmed.replace(/\/$/, '') : null
}

function defaultBardoProxyUrl(nodeEnv: string | undefined): string | null {
  if (nodeEnv === 'production') return null
  return 'http://127.0.0.1:5175/bardo'
}

function defaultPantheonProxyUrl(nodeEnv: string | undefined): string | null {
  if (nodeEnv === 'production') return null
  return 'http://127.0.0.1:5176/pantheon'
}

function defaultDiagnoseProxyUrl(nodeEnv: string | undefined): string | null {
  if (nodeEnv === 'production') return null
  return 'http://127.0.0.1:5177/diagnose'
}

function appendProxyRewrites(rewrites: DashboardRewrite[], pathPrefix: string, resolvedProxyUrl: string | null): void {
  if (!resolvedProxyUrl) return
  rewrites.push(
    {
      source: `/${pathPrefix}`,
      destination: resolvedProxyUrl,
    },
    {
      source: `/${pathPrefix}/:path*`,
      destination: `${resolvedProxyUrl}/:path*`,
    }
  )
}

export function dashboardRewrites({
  bardoProxyUrl,
  pantheonProxyUrl,
  diagnoseProxyUrl,
  nodeEnv,
}: {
  bardoProxyUrl?: string
  pantheonProxyUrl?: string
  diagnoseProxyUrl?: string
  nodeEnv?: string
}): DashboardRewrite[] {
  const rewrites: DashboardRewrite[] = [
    {
      source: '/policy-dashboard',
      destination: '/',
    },
    {
      source: '/policy-dashboard/:path*',
      destination: '/:path*',
    },
  ]

  appendProxyRewrites(rewrites, 'bardo', trimToNull(bardoProxyUrl) ?? defaultBardoProxyUrl(nodeEnv))
  appendProxyRewrites(rewrites, 'pantheon', trimToNull(pantheonProxyUrl) ?? defaultPantheonProxyUrl(nodeEnv))
  appendProxyRewrites(rewrites, 'diagnose', trimToNull(diagnoseProxyUrl) ?? defaultDiagnoseProxyUrl(nodeEnv))

  return rewrites
}
