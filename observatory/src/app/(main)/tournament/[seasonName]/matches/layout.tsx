import { Card } from '@/components/Card'

export default function MatchesLayout({ children }: { children: React.ReactNode }) {
  return <Card title="Matches">{children}</Card>
}

export async function generateMetadata({ params }: PageProps<'/tournament/[seasonName]/matches'>) {
  const { seasonName } = await params
  return {
    title: `Matches for Season ${seasonName} | Observatory`,
  }
}
