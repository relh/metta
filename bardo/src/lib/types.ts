export type BardoPolicy = {
  policyId: string
  policyVersionId: string
  name: string
  userId: string
  userName: string
  createdAt: string
  activeJobIds: string[]
  seasonIds: string[]
}

export type BardoActiveJob = {
  id: string
  status: string
  policyVersionIds: string[]
}

export type BardoSeason = {
  seasonId: string
  name: string
  version: number
  compatVersion: string | null
  createdAt: string
  stageCount: number
  entrantCount: number
  activeEntrantCount: number
}

export type BardoWorldState = {
  generatedAt: string
  totalPolicies: number
  policies: BardoPolicy[]
  activeJobs: BardoActiveJob[]
  seasons: BardoSeason[]
}
