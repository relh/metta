"use client";
import { useSelectedLayoutSegment } from "next/navigation";
import { FC } from "react";

import { LinkButton } from "@/components/LinkButton";

type JobInfo = {
  slug: string;
  name: string;
};

export const TabbedJobs: FC<{ jobs: JobInfo[] }> = ({ jobs }) => {
  const segment = useSelectedLayoutSegment();

  return (
    <div className="flex flex-wrap gap-2">
      {jobs.map((job) => (
        <LinkButton
          key={job.slug}
          href={`/jobs/${job.slug}`}
          theme={segment === job.slug ? "primary" : "outline"}
        >
          {job.name}
        </LinkButton>
      ))}
    </div>
  );
};
