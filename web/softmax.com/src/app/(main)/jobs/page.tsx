import { redirect } from "next/navigation";

import { getJobs } from "./utils";

export const metadata = {
  title: "Softmax - Jobs",
};

export default async function JobsPage() {
  const jobs = await getJobs();
  const jobId = jobs[0].slug;

  redirect(`/jobs/${jobId}`);
}
