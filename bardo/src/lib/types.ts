export type BardoPolicy = {
  policyId: string
  policyVersionId: string
  name: string
  userId: string
  userName: string
  createdAt: string
  activeJobIds: string[]
}

export type BardoActiveJob = {
  id: string
  status: string
  policyVersionIds: string[]
}

export type BardoWorldState = {
  generatedAt: string
  policies: BardoPolicy[]
  activeJobs: BardoActiveJob[]
}
