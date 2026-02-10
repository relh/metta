import { FC, Suspense } from 'react'

import { Card } from '@/components/Card'
import { Spinner } from '@/components/Spinner'
import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { getRepo } from '@/lib/repo/server'

import { matchesRoute } from './matches/utils'
import { formatPolicyDisplay } from './utils'

const LeaderboardContent: FC<{ seasonName: string }> = async ({ seasonName }) => {
  const repo = await getRepo()
  const leaderboard = await repo.getSeasonLeaderboard(seasonName)
  if (leaderboard.length === 0) {
    return (
      <TR>
        <TD colSpan={3} className="text-foreground-muted py-4 text-center">
          No entries yet
        </TD>
      </TR>
    )
  }

  return (
    <>
      {leaderboard.map((entry) => (
        <TR key={entry.policy.id}>
          <TD>{entry.rank}</TD>
          <TD>
            <StyledLink href={`/policies/versions/${entry.policy.id}`} className="font-medium">
              {formatPolicyDisplay(entry)}
            </StyledLink>
          </TD>
          <TD>
            {entry.score.toPrecision(4)}{' '}
            <StyledLink
              href={matchesRoute(seasonName, {
                pool_names: ['competition'],
                policy_version_ids: [entry.policy.id],
              })}
              theme="muted"
              className="text-foreground-muted"
            >
              ({entry.matches} matches)
            </StyledLink>
          </TD>
        </TR>
      ))}
    </>
  )
}

export default async function SeasonPage({ params }: PageProps<'/tournament/[seasonName]'>) {
  const { seasonName } = await params

  return (
    <Card title="Leaderboard">
      <Table>
        <TableHeader>
          <TH>Rank</TH>
          <TH>Policy</TH>
          <TH>Score</TH>
        </TableHeader>
        <TableBody>
          <Suspense
            fallback={
              <TR>
                <TD colSpan={3} className="text-center">
                  <div className="grid place-items-center min-h-80">
                    <Spinner size="lg" />
                  </div>
                </TD>
              </TR>
            }
          >
            <LeaderboardContent seasonName={seasonName} />
          </Suspense>
        </TableBody>
      </Table>
    </Card>
  )
}
