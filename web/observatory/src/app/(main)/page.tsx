import { redirect } from 'next/navigation'

import { policiesRoute } from '@/lib/routes'

export default function Home() {
  redirect(policiesRoute())
}
