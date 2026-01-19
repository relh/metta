import { Spinner } from '@/components/Spinner'

export default function EpisodeJobsLoading() {
  return (
    <div className="grid place-items-center min-h-80">
      <Spinner size="lg" />
    </div>
  )
}
