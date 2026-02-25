import { Metadata } from "next";
import { redirect } from "next/navigation";

import { getJob, getJobs } from "../utils";

export default async function JobPostPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  try {
    const job = await getJob(slug);
    return job.content;
  } catch (error) {
    redirect("/jobs");
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const job = await getJob(slug);
  return {
    title: `Softmax - ${job.frontmatter.name}`,
  };
}

export async function generateStaticParams() {
  const jobs = await getJobs();
  return jobs.map((job) => ({ slug: job.slug }));
}
