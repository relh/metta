export type SeasonTabMode = 'freeplay' | 'tournament'

export const TOURNAMENT_DEFAULT_SEASON_NAME = 'beta-teams-small'
const TOURNAMENT_TAB_SEASON_NAMES = new Set(['beta-teams-small', 'beta-teams-large'])

export const seasonNameFromRef = (seasonRef: string): string => {
  const withV = seasonRef.lastIndexOf(':v')
  if (withV > 0) {
    return seasonRef.slice(0, withV)
  }
  const plain = seasonRef.lastIndexOf(':')
  if (plain > 0) {
    const suffix = seasonRef.slice(plain + 1)
    if (/^\d+$/.test(suffix)) {
      return seasonRef.slice(0, plain)
    }
  }
  return seasonRef
}

export const seasonTabModeForName = (seasonName: string): SeasonTabMode =>
  TOURNAMENT_TAB_SEASON_NAMES.has(seasonNameFromRef(seasonName)) ? 'tournament' : 'freeplay'
