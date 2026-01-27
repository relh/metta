import clsx from "clsx";
import { PropsWithChildren } from "react";

import { Container } from "@/components/Container";
import { Waveform } from "@/components/Waveform";

import { ApplyButton } from "./ApplyButton";
import { TabbedJobs } from "./TabbedJobs";
import { getJobs } from "./utils";

export default async function JobsLayout({ children }: PropsWithChildren) {
  const jobs = await getJobs();

  return (
    <Container>
      <div className="my-8 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-[2em] font-bold">Open Positions</h1>

        <TabbedJobs
          jobs={jobs.map((job) => ({
            slug: job.slug,
            name: job.frontmatter.name,
          }))}
        />
      </div>

      <div
        className={clsx(
          "bg-linear-to-br from-softblue-300/5 to-softblue-400/8",
          "rounded-xl",
          "mb-12 px-5 xs:px-8",
          "border border-softblue-300/15",
        )}
      >
        {children}

        <div className="my-8 text-center">
          <ApplyButton />
        </div>
      </div>
      <Waveform />
    </Container>
  );
}
