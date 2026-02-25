import { Spinner } from "@observatory/components/Spinner";

export default function EpisodeJobsLoading() {
  return (
    <div className="grid min-h-80 place-items-center">
      <Spinner size="lg" />
    </div>
  );
}
