interface Config {
  apiBaseUrl: string
  authServerUrl: string
  authToken?: string
  siteUrl: string
}

export const config: Config = {
  apiBaseUrl: process.env.OBSERVATORY_API_URL || 'http://localhost:8000',
  authToken: process.env.DEV_AUTH_TOKEN, // set in dev mode for convenience based on ~/.metta/config.yaml token
  authServerUrl: process.env.AUTH_SERVER_URL || 'https://softmax.com/api',
  siteUrl: process.env.SITE_URL || 'http://localhost:3000',
}
