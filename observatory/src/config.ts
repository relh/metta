interface Config {
  apiBaseUrl: string
  authServerUrl: string
  authToken?: string
  siteUrl: string
}

export const config: Config = {
  apiBaseUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  authToken: process.env.NEXT_PUBLIC_AUTH_TOKEN, // set in dev mode for convenience based on ~/.metta/config.yaml token
  authServerUrl: process.env.NEXT_PUBLIC_AUTH_SERVER_URL || 'https://softmax.com/api',
  siteUrl: process.env.NEXT_PUBLIC_URL || 'http://localhost:3000',
}
